"""Anthropic Claude API service with optional Tavily tool support"""
import json
from collections.abc import Callable

from anthropic import Anthropic

from app.config import get_api_keys


def _get_tools_if_available():
    """Return Tavily tools if API key is configured."""
    if not get_api_keys().get("tavily"):
        return []
    try:
        from app.services.tavily_service import TAVILY_TOOLS_ANTHROPIC, execute_tool
        return TAVILY_TOOLS_ANTHROPIC, execute_tool
    except Exception:
        return []


class AnthropicService:
    def __init__(self):
        api_key = get_api_keys().get("anthropic")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        self.client = Anthropic(api_key=api_key)

    def chat(
        self,
        messages: list[dict],
        model_id: str = "claude-sonnet-4-6",
        use_tools: bool = True,
        on_status: Callable[[str], None] | None = None,
    ) -> str:
        def status(msg: str) -> None:
            if on_status:
                on_status(msg)

        tools_data = _get_tools_if_available() if use_tools else []
        tools, execute_tool = tools_data if tools_data else ([], None)

        system = "You are a helpful AI assistant."
        anthropic_messages = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                anthropic_messages.append({"role": role, "content": content})

        kwargs = {
            "model": model_id,
            "max_tokens": 4096,
            "system": system,
            "messages": anthropic_messages,
        }
        if tools:
            kwargs["tools"] = tools

        max_iterations = 10
        for _ in range(max_iterations):
            status(f"LLM ({model_id})...")
            response = self.client.messages.create(**kwargs)

            text_parts = []
            tool_use_blocks = []
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    text_parts.append(block.text)
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                status("Done")
                return "".join(text_parts)

            status(f"Tools: {len(tool_use_blocks)}")
            assistant_content = []
            for b in response.content:
                if hasattr(b, "type") and getattr(b, "type", None) == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": b.id,
                        "name": b.name,
                        "input": getattr(b, "input", {}) or {},
                    })
                elif hasattr(b, "text") and getattr(b, "text", None):
                    assistant_content.append({"type": "text", "text": b.text})
            anthropic_messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in tool_use_blocks:
                name = block.name
                tool_id = block.id
                args = getattr(block, "input", {}) or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                q = args.get("query", "")
                urls = args.get("urls", [])
                tool_desc = q if q else (urls[0] if urls else "extracting")[:50]
                status(f"Tavily {name}: {tool_desc[:35]}")
                result = execute_tool(name, args)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result if isinstance(result, str) else str(result),
                })

            anthropic_messages.append({
                "role": "user",
                "content": tool_results,
            })

            kwargs["messages"] = anthropic_messages

        status("Max iterations reached")
        return "I encountered an issue processing your request. Please try again."
