"""Text formatters for agent-facing tool results (task content only)."""

from __future__ import annotations

from typing import Any


def _s(value: Any) -> str:
    return str(value or "").strip()


def format_search_output(result: dict[str, Any], *, for_mcp: bool = False) -> str:
    """Inline search hits: title, url, snippet. No routing metadata."""
    del for_mcp  # kept for call-site compatibility
    results = result.get("results") or []
    error = result.get("error")

    if error and not results:
        return f"Search failed: {_s(error)}"
    if not results:
        return "No results."

    lines: list[str] = []
    for i, item in enumerate(results, 1):
        title = _s(item.get("title")) or "(untitled)"
        url = _s(item.get("url"))
        body = _s(item.get("snippet") or item.get("content") or item.get("raw"))
        lines.append(f"{i}. {title}")
        if url:
            lines.append(f"   {url}")
        if body:
            for line in body.splitlines():
                lines.append(f"   {line}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_extract_output(result: dict[str, Any]) -> str:
    """Inline page bodies. No routing metadata."""
    items = result.get("results") or result.get("result_files") or []
    if not items:
        return "No content."

    parts: list[str] = []
    for item in items:
        url = _s(item.get("url"))
        title = _s(item.get("title"))
        err = item.get("error")
        parts.append(f"## {title or url or 'page'}")
        if url:
            parts.append(url)
        if err:
            parts.append(f"error: {_s(err)}")
            parts.append("")
            continue
        content = _s(item.get("content"))
        parts.append(content or "(empty)")
        parts.append("")
    return "\n".join(parts).rstrip()


def format_research_output(result: dict[str, Any]) -> str:
    """Inline research report and source URLs. Surface degrade notice when present."""
    topic = _s(result.get("topic"))
    report = _s(result.get("report") or result.get("content"))
    sources = [s for s in (result.get("sources") or []) if _s(s)]
    error = result.get("error")
    notice = _s(result.get("notice"))
    degraded = bool(result.get("degraded"))
    warnings = [_s(w) for w in (result.get("warnings") or []) if _s(w)]

    lines: list[str] = []
    if topic:
        lines.extend([f"# {topic}", ""])
    if error and not report:
        lines.append(f"Research failed: {_s(error)}")
        return "\n".join(lines).rstrip()
    if degraded or notice:
        lines.append(f"> {notice or 'research degraded to search summary'}")
        lines.append("")
    elif warnings:
        # Only surface the first warning when not already covered by notice
        lines.append(f"> {warnings[0]}")
        lines.append("")
    lines.append(report or "(empty)")
    if sources:
        lines.append("")
        lines.append("## sources")
        for s in sources:
            lines.append(f"- {s}")
    return "\n".join(lines).rstrip()


def format_docs_search_output(result: dict[str, Any]) -> str:
    """Inline Context7 library search hits."""
    hits = result.get("results") or []
    if not hits:
        return "No matching libraries found."

    lines: list[str] = []
    for i, item in enumerate(hits, 1):
        lib_id = _s(item.get("id"))
        title = _s(item.get("title")) or lib_id
        desc = _s(item.get("description"))
        meta_parts: list[str] = []
        if item.get("total_snippets"):
            meta_parts.append(f"snippets={item['total_snippets']}")
        if item.get("benchmark_score") is not None:
            meta_parts.append(f"score={item['benchmark_score']}")
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        lines.append(f"{i}. {title} — `{lib_id}`{meta}")
        if desc:
            lines.append(f"   {desc}")
    return "\n".join(lines).rstrip()


def format_docs_context_output(result: dict[str, Any]) -> str:
    """Inline Context7 docs context."""
    lib_id = _s(result.get("library_id"))
    content = _s(result.get("content"))
    if not content:
        return f"No documentation found for {lib_id or 'library'}."
    if lib_id:
        return f"# {lib_id}\n\n{content}"
    return content


MCP_SERVER_INSTRUCTIONS = """Tool results are full text inline. Use each tool according to its own description.
"""
