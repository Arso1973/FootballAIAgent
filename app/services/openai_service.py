"""OpenAI API service with optional Tavily tool support"""
from collections.abc import Callable

from openai import OpenAI

from app.config import get_api_keys


def _get_tools_if_available():
    """Return Tavily tools if API key is configured."""
    if not get_api_keys().get("tavily"):
        return []
    try:
        from app.services.tavily_service import TAVILY_TOOLS_OPENAI, execute_tool
        return TAVILY_TOOLS_OPENAI, execute_tool
    except Exception:
        return []


class OpenAIService:
    def __init__(self):
        api_key = get_api_keys().get("openai")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        self.client = OpenAI(api_key=api_key)

    def chat(
        self,
        messages: list[dict],
        model_id: str = "gpt-4o",
        use_tools: bool = True,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        def status(msg: str) -> None:
            if on_status:
                on_status(msg)

        tools_data = _get_tools_if_available() if use_tools else []
        tools, execute_tool = tools_data if tools_data else ([], None)

        kwargs: dict = {
            "model": model_id,
            "messages": messages,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        max_iterations = 10
        for _ in range(max_iterations):
            status(f"LLM ({model_id})...")
            response = self.client.chat.completions.create(**kwargs)

            msg = response.choices[0].message
            if not msg.tool_calls:
                status("Done")
                return (msg.content or "").strip()

            status(f"Tools: {len(msg.tool_calls)}")
            messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                name = tc.function.name
                args = {}
                try:
                    import json
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    pass
                q = args.get("query", "")
                urls = args.get("urls", [])
                tool_desc = q if q else (urls[0] if urls else "extracting")[:50]
                status(f"Tavily {name}: {tool_desc[:35]}")
                result = execute_tool(name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            kwargs["messages"] = messages
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)

        status("Max iterations reached")
        return "I encountered an issue processing your request. Please try again."
