"""Assemble protocol hits/pages from adapter-local values."""

from __future__ import annotations

from typing import Any

from ..models.search import ExtractPage, SearchHit


def text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            joined = "\n".join(str(v).strip() for v in value if v is not None and str(v).strip())
            if joined:
                return joined
            continue
        s = str(value).strip()
        if s:
            return s
    return ""


def attr(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for name in names:
            if name in obj and obj[name] is not None:
                return obj[name]
        return default
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def make_hit(
    *,
    title: Any = "",
    url: Any = "",
    snippet: Any = "",
    score: Any = 0.0,
    source: str,
    published_at: Any = None,
    author: Any = None,
    raw: Any = None,
) -> SearchHit:
    try:
        score_f = float(score or 0.0)
    except (TypeError, ValueError):
        score_f = 0.0
    return SearchHit(
        title=text(title) or "(untitled)",
        url=text(url),
        snippet=text(snippet),
        score=score_f,
        source=source,
        published_at=text(published_at) or None,
        author=text(author) or None,
        raw=text(raw) or None,
    )


def make_page(
    *,
    url: Any,
    content: Any = "",
    title: Any = None,
    error: Any = None,
) -> ExtractPage:
    err = text(error) or None
    return ExtractPage(
        url=text(url),
        content="" if err else text(content),
        title=text(title) or None,
        error=err,
    )


def urls_from_sources(sources: Any) -> list[str]:
    out: list[str] = []
    if not sources:
        return out
    if not isinstance(sources, list):
        sources = [sources]
    for item in sources:
        if isinstance(item, str):
            u = item.strip()
            if u:
                out.append(u)
            continue
        u = text(attr(item, "url", "link", "href"))
        if u:
            out.append(u)
    seen: set[str] = set()
    unique: list[str] = []
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)
    return unique


def optional_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    cleaned = [v.strip() for v in values if v and str(v).strip()]
    return cleaned or None
