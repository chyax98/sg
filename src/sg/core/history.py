"""Search history — view (for AI) is truth, trace (for indexing) is auxiliary."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..models.config import HistoryConfig
from ..models.search import HistoryEntry, SearchRequest, SearchResponse, SearchResult

logger = logging.getLogger(__name__)


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
            results.append(SearchResult(
                title=data.get("title", ""),
                url=data.get("url", ""),
                content=data.get("content", ""),
                snippet=data.get("content", ""),
                score=data.get("score", 0.0),
                source=provider,
                published_date=data.get("published_date"),
                author=data.get("author"),
            ))
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
        entry_id = f"{ts}-{uuid.uuid4().hex[:4]}"
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
                trace_file.write_text,
                json.dumps(trace_data, ensure_ascii=False)
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

        Same storage structure as search - JSONL format for unified handling.
        Returns view file path.
        """
        now = datetime.now()
        ts = int(time.time() * 1000)
        entry_id = f"{ts}-{uuid.uuid4().hex[:4]}"
        month = now.strftime("%Y-%m")

        view_month, trace_month = self._ensure_dirs(month)
        view_file = view_month / f"{entry_id}.txt"
        trace_file = trace_month / f"{entry_id}.json"

        # Write view file (JSONL format, same as search)
        # Single entry with operation info in title
        view_data = {
            "index": 1,
            "title": f"[{operation.upper()}] {query[:80]}",
            "url": "",
            "content": content,
        }
        view_content = json.dumps(view_data, ensure_ascii=False)

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
            await asyncio.to_thread(view_file.write_text, view_content)
            await asyncio.to_thread(
                trace_file.write_text,
                json.dumps(trace_data, ensure_ascii=False)
            )
            logger.debug(f"Content saved: id={entry_id}, operation={operation}")
            return str(view_file)
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            raise

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
                parsed_entries.append(HistoryEntry(
                    id=data["id"],
                    query=data["query"],
                    provider=data["provider"],
                    total=data["total"],
                    latency_ms=data["latency_ms"],
                    timestamp=data["timestamp"],
                    results=None,
                ))
            except (json.JSONDecodeError, KeyError):
                continue

        parsed_entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        return parsed_entries[offset:offset + limit]

    async def get(self, entry_id: str):
        """Get full entry by reading view file (truth source)."""
        # Extract pure id from path or id string
        entry_path = Path(entry_id)
        pure_id = entry_path.stem if entry_path.suffix in ('.txt', '.json') else entry_id

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

            # Read view file for results (TRUTH SOURCE)
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
                results=results,
            )
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
