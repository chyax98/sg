"""Structured text output helpers for AI agent consumption."""

from typing import Any


def _inline(value: Any) -> str:
    text = str(value or "")
    return text.replace("\n", " ").strip()


def _truncate(text: str, limit: int = 50) -> str:
    text = _inline(text)
    return text if len(text) <= limit else text[:limit] + "..."


def format_search_output(result: dict[str, Any], max_preview: int = 5) -> str:
    """Format search results for predictable agent parsing."""
    query = result.get("query", "")
    result_file = result.get("result_file", "")
    results = result.get("results", []) or []
    total = result.get("total", len(results))
    error = result.get("error")

    lines = ["type: search", f"query: {query}"]
    if error:
        lines.append(f"error: {_inline(error)}")
        return "\n".join(lines)

    if result_file:
        lines.append(f"file: {result_file}")
        lines.append("next: read_file")

    preview_count = min(len(results), max_preview)
    lines.append("")
    lines.append(f"preview[{preview_count}]{{line,title,url,score}}:")

    for i, item in enumerate(results[:preview_count], 1):
        score = item.get("score")
        score_str = f"{score:.2f}" if score else "-"
        lines.append(
            f"  {i},{_truncate(item.get('title', ''))},{_inline(item.get('url', ''))},{score_str}"
        )

    if total > preview_count:
        lines.append(f"  ... ({total - preview_count} more)")

    if result_file:
        lines.append("")
        lines.append("note: file line number equals result index")

    return "\n".join(lines)


def format_extract_output(result: dict[str, Any]) -> str:
    """Format extract results for predictable agent parsing."""
    result_files = result.get("result_files", []) or []
    raw_results = result.get("results", []) or []
    item_count = len(result_files) or len(raw_results)

    lines = ["type: extract", f"items: {item_count}"]

    ok_files = [item for item in result_files if item.get("file") and not item.get("error")]
    error_items = [item for item in result_files if item.get("error")]

    if ok_files:
        lines.append("next: read_file")
        lines.append("")
        lines.append(f"files[{len(ok_files)}]{{idx,file,chars,lines,title}}:")
        for idx, item in enumerate(ok_files, 1):
            lines.append(
                f"  {idx},{item.get('file', '')},{item.get('chars', 0)}c,{item.get('lines', 0)}L,{_truncate(item.get('title', ''))}"
            )
            lines.append(f"    {_inline(item.get('url', ''))}")
    elif raw_results:
        lines.append("")
        lines.append(f"preview[{len(raw_results)}]{{idx,url,chars,title}}:")
        for idx, item in enumerate(raw_results, 1):
            lines.append(
                f"  {idx},{_inline(item.get('url', ''))},{len(item.get('content', ''))}c,{_truncate(item.get('title', ''))}"
            )

    if not error_items:
        error_items = [item for item in raw_results if item.get("error")]

    if error_items:
        lines.append("")
        lines.append(f"errors[{len(error_items)}]{{idx,url,error}}:")
        for idx, item in enumerate(error_items, 1):
            lines.append(f"  {idx},{_inline(item.get('url', ''))},{_inline(item.get('error', ''))}")

    return "\n".join(lines)


def format_research_output(result: dict[str, Any], preview_chars: int = 1000) -> str:
    """Format research results for predictable agent parsing."""
    topic = result.get("topic", "")
    result_file = result.get("result_file", "")
    content = result.get("content", "") or ""
    total_lines = content.count("\n") + 1 if content else 0

    lines = ["type: research", f"topic: {topic}"]
    if result_file:
        lines.append(f"file: {result_file}")
        lines.append("next: read_file")
    lines.append(f"size: {len(content)}c {total_lines}L")
    lines.append("")
    lines.append("preview:")
    lines.append(
        content[:preview_chars] + ("\n\n...(truncated)..." if len(content) > preview_chars else "")
    )
    return "\n".join(lines)
