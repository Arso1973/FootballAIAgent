"""Tavily service - web search and content extraction via MCP or direct API"""
import json
from typing import Any

from app.config import get_api_keys


def _get_tavily_api_key() -> str:
    api_key = get_api_keys().get("tavily")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not set in .env")
    return api_key


def _tavily_search_sdk(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """Fallback: use Tavily Python SDK directly."""
    from tavily import TavilyClient
    client = TavilyClient(api_key=_get_tavily_api_key())
    response = client.search(query, max_results=max_results, search_depth=search_depth)
    results = response.get("results", [])
    if not results:
        return "No results found."
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")
        parts.append(f"[{i}] {title}\nURL: {url}\n{content}")
    return "\n\n---\n\n".join(parts)


def _tavily_extract_sdk(urls: list[str], query: str | None = None) -> str:
    """Fallback: use Tavily Python SDK for extract."""
    from tavily import TavilyClient
    client = TavilyClient(api_key=_get_tavily_api_key())
    response = client.extract(urls, query=query)
    results = response.get("results", [])
    if not results:
        return "No content extracted."
    parts = []
    for r in results:
        url = r.get("url", "")
        raw = r.get("raw_content", r.get("content", ""))
        parts.append(f"URL: {url}\n\n{raw}")
    return "\n\n---\n\n".join(parts)


def tavily_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
) -> str:
    """Search the web using Tavily."""
    try:
        import asyncio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={_get_tavily_api_key()}"

        async def _call():
            async with streamable_http_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "tavily-search",
                        arguments={"query": query, "max_results": max_results, "search_depth": search_depth},
                    )
                    if result.isError:
                        raise RuntimeError(str(result.content))
                    parts = []
                    for block in result.content:
                        if hasattr(block, "text"):
                            parts.append(block.text)
                    return "\n\n".join(parts) if parts else json.dumps(result.content)

        return asyncio.run(_call())
    except Exception:
        return _tavily_search_sdk(query, max_results, search_depth)


def tavily_extract(
    urls: list[str],
    query: str | None = None,
) -> str:
    """Extract and summarize content from one or more URLs."""
    args: dict[str, Any] = {"urls": urls}
    if query:
        args["query"] = query
    try:
        import asyncio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        url = f"https://mcp.tavily.com/mcp/?tavilyApiKey={_get_tavily_api_key()}"

        async def _call():
            async with streamable_http_client(url) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool("tavily-extract", arguments=args)
                    if result.isError:
                        raise RuntimeError(str(result.content))
                    parts = []
                    for block in result.content:
                        if hasattr(block, "text"):
                            parts.append(block.text)
                    return "\n\n".join(parts) if parts else json.dumps(result.content)

        return asyncio.run(_call())
    except Exception:
        return _tavily_extract_sdk(urls, query)


TAVILY_TOOLS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "Search the web for current information, facts, news, or URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tavily_extract",
            "description": "Extract content from one or more URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "List of URLs"},
                    "query": {"type": "string", "description": "Optional extraction focus"},
                },
                "required": ["urls"],
            },
        },
    },
]

TAVILY_TOOLS_ANTHROPIC = [
    {
        "name": "tavily_search",
        "description": "Search the web for current information, facts, news, or URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "default": 5},
                "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "tavily_extract",
        "description": "Extract content from one or more URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}},
                "query": {"type": "string"},
            },
            "required": ["urls"],
        },
    },
]


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a Tavily tool by name."""
    if name == "tavily_search":
        return tavily_search(
            query=arguments.get("query", ""),
            max_results=arguments.get("max_results", 5),
            search_depth=arguments.get("search_depth", "basic"),
        )
    elif name == "tavily_extract":
        return tavily_extract(
            urls=arguments.get("urls", []),
            query=arguments.get("query"),
        )
    else:
        return f"Unknown tool: {name}"
