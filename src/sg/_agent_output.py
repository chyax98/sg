"""Structured text output helpers for AI agent consumption."""

from typing import Any


def _inline(value: Any) -> str:
    text = str(value or "")
    return text.replace("\n", " ").strip()


def format_search_output(result: dict[str, Any], *, for_mcp: bool = False) -> str:
    """Inline all search hits (title, url, snippet). No file pointer."""
    query = result.get("query", "")
    results = result.get("results", []) or []
    total = result.get("total", len(results))
    error = result.get("error")
    provider = result.get("provider", "")

    lines = ["type: search", f"query: {query}"]
    if provider:
        lines.append(f"provider: {provider}")
    if error:
        lines.append(f"error: {_inline(error)}")
        return "\n".join(lines)

    lines.append(f"total: {total}")
    if for_mcp:
        lines.append(
            "note: Answer from the snippets below. Do not call extract on these URLs unless the user needs full page text."
        )
    lines.append("")

    for i, item in enumerate(results, 1):
        body = (item.get("content") or item.get("snippet") or "").strip()
        lines.append(f"--- result {i} ---")
        lines.append(f"title: {item.get('title', '')}")
        lines.append(f"url: {item.get('url', '')}")
        if item.get("published_date"):
            lines.append(f"published: {item.get('published_date')}")
        if item.get("score"):
            lines.append(f"score: {item.get('score')}")
        lines.append("snippet:")
        lines.append(body if body else "(empty)")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_extract_output(result: dict[str, Any]) -> str:
    """Inline extracted page content per URL."""
    raw_results = result.get("results", []) or []
    result_files = result.get("result_files", []) or []
    provider = result.get("provider", "")

    if raw_results:
        items = raw_results
    else:
        items = result_files

    lines = ["type: extract", f"items: {len(items)}"]
    if provider:
        lines.append(f"provider: {provider}")
    lines.append("")

    for i, item in enumerate(items, 1):
        url = item.get("url", "")
        err = item.get("error")
        if err:
            lines.append(f"--- item {i} ---")
            lines.append(f"url: {url}")
            lines.append(f"error: {_inline(err)}")
            lines.append("")
            continue

        content = (item.get("content") or "").strip()
        title = item.get("title") or ""
        lines.append(f"--- item {i} ---")
        lines.append(f"url: {url}")
        if title:
            lines.append(f"title: {title}")
        lines.append("content:")
        lines.append(content if content else "(empty)")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_research_output(result: dict[str, Any]) -> str:
    """Inline full research report."""
    topic = result.get("topic", "")
    content = (result.get("content", "") or "").strip()
    provider = result.get("provider", "")

    lines = ["type: research", f"topic: {topic}"]
    if provider:
        lines.append(f"provider: {provider}")
    lines.append("")
    lines.append("report:")
    lines.append(content if content else "(empty)")
    return "\n".join(lines)


MCP_SERVER_INSTRUCTIONS = """Search Gateway MCP tools return full text inline (search snippets, extract body, research report).
Use the tool output directly. Do not follow up with read_file on disk paths.
Use extract only when the user needs full page content for a specific URL — not as a default after search.
Prefer automatic provider routing; omit the provider argument unless the user asks for one.
"""
