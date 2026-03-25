"""Search history — view (for AI) is truth, trace (for indexing) is auxiliary."""

import asyncio
import json
import logging
import textwrap
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..models.config import HistoryConfig
from ..models.search import HistoryEntry, SearchRequest, SearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Max characters per line for view files.
# AI tools like view_file are line-based, so shorter lines = better random access.
_LINE_WIDTH = 200


def _wrap_content(content: str) -> str:
    """Wrap long lines for AI-friendly line-based access.

    Preserves existing newlines and markdown structure.
    Only wraps lines exceeding _LINE_WIDTH characters.
    """
    out_lines: list[str] = []
    for line in content.split("\n"):
        if len(line) <= _LINE_WIDTH:
            out_lines.append(line)
        else:
            # Wrap long lines, preserving leading whitespace
            wrapped = textwrap.fill(
                line,
                width=_LINE_WIDTH,
                break_long_words=False,
                break_on_hyphens=False,
            )
            out_lines.extend(wrapped.split("\n"))
    return "\n".join(out_lines)

def _format_view_content(response: SearchResponse) -> str:
    """Format search results as JSONL - each line is a complete result.

    This is the TRUTH SOURCE. Full content preserved, line-oriented for selective reading.
    """
    lines = []
    for i, r in enumerate(response.results, 1):
        data = {
            "index": i,
            "title": r.title,
            "url": r.url,
            "content": r.content or r.snippet or "",
        }
        if r.score:
            data["score"] = r.score
        if r.published_date:
            data["published_date"] = r.published_date
        if r.author:
            data["author"] = r.author
        lines.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(lines)


def _parse_view_content(view_text: str, provider: str = "") -> list[SearchResult]:
    """Parse JSONL view file back into SearchResult objects."""
    results = []
    for line in view_text.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            results.append(
                SearchResult(
                    title=data.get("title", ""),
                    url=data.get("url", ""),
                    content=data.get("content", ""),
                    snippet=data.get("content", ""),
                    score=data.get("score", 0.0),
                    source=provider,
                    published_date=data.get("published_date"),
                    author=data.get("author"),
                )
            )
        except json.JSONDecodeError:
            continue
    return results


class SearchHistory:
    """Filesystem-backed search history.

    - view/: Compact text format, TRUTH SOURCE for AI and data
    - trace/: Metadata index for listing (auxiliary, can be rebuilt from view)
    """

    def __init__(self, config: HistoryConfig):
        self.dir = Path(config.dir).expanduser()
        self.view_dir = self.dir / "view"
        self.trace_dir = self.dir / "trace"
        self.max_entries = config.max_entries

    def _ensure_dirs(self, month: str):
        view_month = self.view_dir / month
        trace_month = self.trace_dir / month
        view_month.mkdir(parents=True, exist_ok=True)
        trace_month.mkdir(parents=True, exist_ok=True)
        return view_month, trace_month

    async def record(self, request: SearchRequest, response: SearchResponse) -> str:
        """Save search result. Returns view file path."""
        now = datetime.now()
        ts = int(time.time() * 1000)
        entry_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        month = now.strftime("%Y-%m")

        view_month, trace_month = self._ensure_dirs(month)
        view_file = view_month / f"{entry_id}.txt"
        trace_file = trace_month / f"{entry_id}.json"

        # Write view file (TRUTH SOURCE)
        view_content = _format_view_content(response)

        # Write trace file (just index metadata, no results)
        trace_data = {
            "id": entry_id,
            "timestamp": now.isoformat(),
            "ts": ts,
            "query": request.query,
            "provider": response.provider,
            "total": response.total,
            "latency_ms": response.latency_ms,
            "view_file": str(view_file),
        }

        try:
            await asyncio.to_thread(view_file.write_text, view_content)
            await asyncio.to_thread(
                trace_file.write_text, json.dumps(trace_data, ensure_ascii=False)
            )
            logger.debug(f"History saved: id={entry_id}, query='{request.query}'")
            return str(view_file)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            raise

    async def record_content(
        self,
        operation: str,  # "extract" or "research"
        query: str,
        provider: str,
        latency_ms: float,
        content: str,  # content to save in view file
    ) -> str:
        """Save content operation with view file (for extract/research).

        Stores as line-wrapped plain text for AI-friendly random access.
        Returns view file path.
        """
        now = datetime.now()
        ts = int(time.time() * 1000)
        entry_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        month = now.strftime("%Y-%m")

        view_month, trace_month = self._ensure_dirs(month)
        view_file = view_month / f"{entry_id}.txt"
        trace_file = trace_month / f"{entry_id}.json"

        # Wrap content for line-based reading
        wrapped = _wrap_content(content)

        # Write trace file (metadata)
        trace_data = {
            "id": entry_id,
            "timestamp": now.isoformat(),
            "ts": ts,
            "operation": operation,
            "query": query,
            "provider": provider,
            "total": 1,
            "latency_ms": latency_ms,
            "view_file": str(view_file),
        }

        try:
            await asyncio.to_thread(view_file.write_text, wrapped)
            await asyncio.to_thread(
                trace_file.write_text, json.dumps(trace_data, ensure_ascii=False)
            )
            logger.debug(f"Content saved: id={entry_id}, operation={operation}")
            return str(view_file)
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            raise

    async def record_extract(
        self,
        urls: list[str],
        results: list,  # list of ExtractResult
        provider: str,
        latency_ms: float,
    ) -> list[dict]:
        """Save extract results as per-URL files with line wrapping.

        Each URL gets its own file with a metadata header + wrapped content.
        Returns list of [{url, title, file, chars, lines, error}].
        """
        now = datetime.now()
        ts = int(time.time() * 1000)
        base_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        month = now.strftime("%Y-%m")
        view_month, trace_month = self._ensure_dirs(month)

        file_manifest: list[dict] = []

        for i, r in enumerate(results):
            suffix = f"-{i + 1}" if len(results) > 1 else ""
            entry_id = f"{base_id}{suffix}"
            view_file = view_month / f"{entry_id}.txt"

            if r.error:
                # Error: minimal file
                content = f"URL: {r.url}\nError: {r.error}\n"
                file_manifest.append({
                    "url": r.url,
                    "title": r.title or "",
                    "file": str(view_file),
                    "chars": 0,
                    "lines": 0,
                    "error": r.error,
                })
            else:
                # Header + wrapped content
                header_lines = [f"URL: {r.url}"]
                if r.title:
                    header_lines.append(f"Title: {r.title}")
                header_lines.append("---")

                wrapped_body = _wrap_content(r.content)
                body_line_count = wrapped_body.count("\n") + 1

                content = "\n".join(header_lines) + "\n" + wrapped_body + "\n"

                file_manifest.append({
                    "url": r.url,
                    "title": r.title or "",
                    "file": str(view_file),
                    "chars": len(r.content),
                    "lines": body_line_count,
                })

            try:
                await asyncio.to_thread(view_file.write_text, content)
            except Exception as e:
                logger.error(f"Failed to save extract file for {r.url}: {e}")
                # Mark manifest entry as failed so AI won't try to read missing file
                file_manifest[-1]["error"] = f"save failed: {e}"
                file_manifest[-1].pop("file", None)

        # Write trace file (one trace for the whole extract operation)
        trace_file = trace_month / f"{base_id}.json"
        trace_data = {
            "id": base_id,
            "timestamp": now.isoformat(),
            "ts": ts,
            "operation": "extract",
            "query": ", ".join(urls)[:100],
            "provider": provider,
            "total": len(results),
            "latency_ms": latency_ms,
            "files": file_manifest,
        }
        try:
            await asyncio.to_thread(
                trace_file.write_text, json.dumps(trace_data, ensure_ascii=False)
            )
        except Exception as e:
            logger.error(f"Failed to save extract trace: {e}")

        return file_manifest

    async def list(self, limit: int = 50, offset: int = 0):
        """List recent entries from trace files (just metadata)."""
        if not self.trace_dir.exists():
            return []

        files = await asyncio.to_thread(lambda: list(self.trace_dir.rglob("*.json")))
        parsed_entries = []

        for f in files:
            try:
                text = await asyncio.to_thread(f.read_text)
                data = json.loads(text)
                parsed_entries.append(
                    HistoryEntry(
                        id=data["id"],
                        query=data["query"],
                        provider=data["provider"],
                        total=data["total"],
                        latency_ms=data["latency_ms"],
                        timestamp=data["timestamp"],
                        operation=data.get("operation", "search"),
                        results=None,
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue

        parsed_entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        return parsed_entries[offset : offset + limit]

    async def get(self, entry_id: str):
        """Get full entry by reading view file (truth source)."""
        # Extract pure id from path or id string
        entry_path = Path(entry_id)
        pure_id = entry_path.stem if entry_path.suffix in (".txt", ".json") else entry_id

        # Find trace file to get metadata and view_file path
        def _find_trace():
            for month_dir in self.trace_dir.iterdir():
                if month_dir.is_dir():
                    trace_file = month_dir / f"{pure_id}.json"
                    if trace_file.exists():
                        return trace_file
            return None

        trace_file = await asyncio.to_thread(_find_trace)
        if not trace_file:
            return None

        try:
            # Read trace for metadata
            trace_text = await asyncio.to_thread(trace_file.read_text)
            trace_data = json.loads(trace_text)
            operation = trace_data.get("operation", "search")

            if operation == "extract" and "files" in trace_data:
                # Extract entries: return file manifest from trace
                return HistoryEntry(
                    id=trace_data["id"],
                    query=trace_data["query"],
                    provider=trace_data["provider"],
                    total=trace_data["total"],
                    latency_ms=trace_data["latency_ms"],
                    timestamp=trace_data["timestamp"],
                    operation=operation,
                    files=trace_data["files"],
                )
            elif "view_file" in trace_data:
                # Search / research entries: parse JSONL view file
                view_file = Path(trace_data["view_file"])
                if not view_file.exists():
                    return None

                view_text = await asyncio.to_thread(view_file.read_text)
                results = _parse_view_content(view_text, trace_data.get("provider", ""))

                return HistoryEntry(
                    id=trace_data["id"],
                    query=trace_data["query"],
                    provider=trace_data["provider"],
                    total=trace_data["total"],
                    latency_ms=trace_data["latency_ms"],
                    timestamp=trace_data["timestamp"],
                    operation=operation,
                    results=results,
                )
            else:
                return None
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return None

    async def clear(self) -> int:
        """Clear all history. Returns count deleted."""
        count = 0

        def _do_clear():
            nonlocal count
            for f in self.trace_dir.rglob("*.json"):
                f.unlink()
                count += 1
            for f in self.view_dir.rglob("*.txt"):
                f.unlink()
                count += 1
            for d in sorted(self.trace_dir.iterdir(), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            for d in sorted(self.view_dir.iterdir(), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            return count

        count = await asyncio.to_thread(_do_clear)
        logger.info(f"History cleared: {count} entries deleted")
        return count
