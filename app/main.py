"""FastAPI application entry point"""
import json
import queue
import uuid
from datetime import datetime
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    ensure_data_dir,
    get_api_keys,
    get_default_model,
    get_models_config,
    HISTORY_FILE,
)
from app.models import ChatMessage, ChatRequest, ChatResponse, ErrorResponse

ensure_data_dir()

app = FastAPI(title="AI Agent", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

_sessions: dict[str, dict] = {}
MAX_TITLE_LENGTH = 50


def _title_from_message(text: str) -> str:
    words = text.split()
    result = []
    length = 0
    for w in words:
        if length + len(w) + 1 > MAX_TITLE_LENGTH:
            break
        result.append(w)
        length += len(w) + 1
    title = " ".join(result) if result else "New chat"
    return (title + "…") if len(text) > len(title) else title


def _get_messages(session_id: str) -> list[dict]:
    data = _sessions.get(session_id)
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return data.get("messages", [])


def _set_messages(session_id: str, messages: list[dict], title: str | None = None):
    existing = _sessions.get(session_id)
    if isinstance(existing, list):
        _sessions[session_id] = {"messages": messages, "title": title or "New chat"}
    else:
        _sessions[session_id] = {
            "messages": messages,
            "title": title or (existing.get("title") if existing else "New chat"),
        }


def _load_sessions():
    global _sessions
    if HISTORY_FILE.exists():
        try:
            raw = json.load(open(HISTORY_FILE, "r", encoding="utf-8"))
            for sid, val in raw.items():
                if isinstance(val, list):
                    title = _title_from_message(val[0]["content"]) if val and val[0].get("role") == "user" else "New chat"
                    raw[sid] = {"messages": val, "title": title}
            _sessions = raw
        except (json.JSONDecodeError, IOError):
            _sessions = {}


def _save_sessions():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(_sessions, f, indent=2, ensure_ascii=False)


_load_sessions()

SYSTEM_PROMPT_PATH = BASE_DIR / "prompts" / "football_betting_agent_prompt.md"


def _get_system_prompt() -> str:
    if SYSTEM_PROMPT_PATH.exists():
        text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        now = datetime.now()
        year = now.year
        # Inject current date context and replace hardcoded year
        text = text.replace("2025", str(year))
        text = f"**Danas je: {now.strftime('%d.%m.%Y')}.**\n\n{text}"
        return text
    return "You are a helpful AI assistant."


def _build_messages_for_llm(history: list, new_message: str) -> list[dict]:
    messages = [{"role": "system", "content": _get_system_prompt()}]
    for h in history:
        role = h.get("role") if isinstance(h, dict) else h.role
        content = h.get("content") if isinstance(h, dict) else h.content
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": new_message})
    return messages


def _get_llm_response(
    model_id: str,
    messages: list[dict],
    on_status: Callable[[str], None] | None = None,
) -> str:
    api_keys = get_api_keys()
    models_config = get_models_config()
    provider = None
    for m in models_config:
        if m.get("id") == model_id:
            provider = m.get("provider")
            break
    if not provider:
        provider = "openai" if "gpt" in model_id.lower() else "anthropic"

    if provider == "openai":
        if not api_keys.get("openai"):
            raise HTTPException(status_code=400, detail="OpenAI API key not configured. Add OPENAI_API_KEY to .env")
        from app.services.openai_service import OpenAIService
        svc = OpenAIService()
        return svc.chat(messages, model_id, on_status=on_status)
    elif provider == "anthropic":
        if not api_keys.get("anthropic"):
            raise HTTPException(status_code=400, detail="Anthropic API key not configured. Add ANTHROPIC_API_KEY to .env")
        from app.services.anthropic_service import AnthropicService
        svc = AnthropicService()
        return svc.chat(messages, model_id, on_status=on_status)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(BASE_DIR / "templates" / "index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/models")
async def list_models():
    models = get_models_config()
    api_keys = get_api_keys()
    for m in models:
        m["available"] = bool(api_keys.get(m.get("provider", ""), ""))
    return {"models": models, "default": get_default_model()}


@app.get("/api/tools")
async def list_tools():
    api_keys = get_api_keys()
    tools = []
    if api_keys.get("tavily"):
        tools.extend([
            {"name": "tavily_search", "description": "Search the web for current information"},
            {"name": "tavily_extract", "description": "Extract content from URLs"},
        ])
    return {"tools": tools}


_executor = ThreadPoolExecutor(max_workers=4)


def _chat_stream_generator(request: ChatRequest) -> Generator[str, None, None]:
    session_id = request.session_id or str(uuid.uuid4())
    messages_list = _get_messages(session_id)
    is_first_message = len(messages_list) == 0

    messages = _build_messages_for_llm(
        [{"role": h.role, "content": h.content} for h in request.history],
        request.message,
    )

    q: queue.Queue = queue.Queue()

    def on_status(msg: str) -> None:
        q.put({"type": "status", "message": msg})

    def run_llm() -> None:
        try:
            on_status("Processing...")
            response_text = _get_llm_response(request.model_id, messages, on_status=on_status)
            messages_list.append({"role": "user", "content": request.message})
            messages_list.append({"role": "assistant", "content": response_text})
            title = _title_from_message(request.message) if is_first_message else None
            _set_messages(session_id, messages_list, title)
            _save_sessions()
            q.put({"type": "done", "content": response_text, "session_id": session_id})
        except HTTPException as he:
            q.put({"type": "error", "detail": str(he.detail)})
        except Exception as e:
            q.put({"type": "error", "detail": str(e)})

    _executor.submit(run_llm)

    while True:
        try:
            item = q.get(timeout=0.2)
        except queue.Empty:
            yield "\n"
            continue
        if item["type"] == "done":
            yield json.dumps({
                "type": "done",
                "content": item["content"],
                "session_id": item["session_id"],
                "model_id": request.model_id,
            }) + "\n"
            break
        if item["type"] == "error":
            yield json.dumps({"type": "error", "detail": item["detail"]}) + "\n"
            break
        yield json.dumps(item) + "\n"


@app.post("/api/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        _chat_stream_generator(request),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    messages_list = _get_messages(session_id)
    is_first_message = len(messages_list) == 0

    messages = _build_messages_for_llm(
        [{"role": h.role, "content": h.content} for h in request.history],
        request.message,
    )

    try:
        response_text = _get_llm_response(request.model_id, messages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    messages_list.append({"role": "user", "content": request.message})
    messages_list.append({"role": "assistant", "content": response_text})
    title = _title_from_message(request.message) if is_first_message else None
    _set_messages(session_id, messages_list, title)
    _save_sessions()

    return ChatResponse(
        content=response_text,
        model_id=request.model_id,
        session_id=session_id,
    )


@app.get("/api/history")
async def get_history(session_id: str | None = None):
    if session_id:
        return {"session_id": session_id, "messages": _get_messages(session_id)}
    sessions = [
        {"id": sid, "title": _sessions[sid].get("title", "New chat") if isinstance(_sessions[sid], dict) else "New chat"}
        for sid in _sessions.keys()
    ]
    return {"sessions": sessions, "count": len(_sessions)}


@app.post("/api/chat/clear")
async def clear_chat(session_id: str | None = None):
    if session_id and session_id in _sessions:
        _set_messages(session_id, [], "New chat")
        _save_sessions()
    return {"ok": True}


@app.patch("/api/chat/rename")
async def rename_chat(session_id: str, title: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    data = _sessions[session_id]
    if isinstance(data, dict):
        data["title"] = (title or "New chat").strip()[:100]
    else:
        _sessions[session_id] = {"messages": data, "title": (title or "New chat").strip()[:100]}
    _save_sessions()
    return {"ok": True, "title": _sessions[session_id].get("title", "New chat")}


@app.delete("/api/chat/{session_id}")
async def delete_chat(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del _sessions[session_id]
    _save_sessions()
    return {"ok": True}


@app.post("/api/chat/new")
async def new_chat():
    session_id = str(uuid.uuid4())
    _set_messages(session_id, [], "New chat")
    _save_sessions()
    return {"session_id": session_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
