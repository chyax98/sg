"""Search history — filesystem-backed, non-blocking I/O."""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from ..models.config import HistoryConfig
from ..models.search import HistoryEntry, SearchRequest, SearchResponse

logger = logging.getLogger(__name__)


class SearchHistory:
    """Filesystem-backed search history with async I/O."""

    def __init__(self, config: HistoryConfig):
        self.dir = Path(config.dir).expanduser()
        self.max_entries = config.max_entries

    def _ensure_dir(self, subdir: str = "") -> Path:
        d = self.dir / subdir if subdir else self.dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def record(self, request: SearchRequest, response: SearchResponse) -> str:
        """Save search result. Returns absolute file path."""
        now = datetime.now()
        entry_id = f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        month_dir = self._ensure_dir(now.strftime("%Y-%m"))

        entry = {
            "id": entry_id,
            "timestamp": now.isoformat(),
            "query": request.query,
            "provider": response.provider,
            "total": response.total,
            "latency_ms": response.latency_ms,
            "results": [r.model_dump() for r in response.results],
        }

        filepath = month_dir / f"{entry_id}.json"
        content = json.dumps(entry, ensure_ascii=False, indent=2)

        try:
            await asyncio.to_thread(filepath.write_text, content)
            logger.debug(f"History saved: query='{request.query}', provider={response.provider}, file={filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            raise

    async def list(self, limit: int = 50, offset: int = 0) -> list[HistoryEntry]:
        """List recent entries (without full results)."""
        if not self.dir.exists():
            return []

        files = await asyncio.to_thread(
            lambda: sorted(self.dir.rglob("*.json"), reverse=True)
        )
        entries = []

        for f in files[offset:offset + limit]:
            try:
                text = await asyncio.to_thread(f.read_text)
                data = json.loads(text)
                entries.append(HistoryEntry(
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

        return entries

    async def get(self, entry_id: str) -> HistoryEntry | None:
        """Get full entry by ID.

        entry_id can be either:
        - A full file path (as returned by record)
        - Just the entry ID (filename without extension)
        """
        if not self.dir.exists() or not self.dir.is_dir():
            return None

        # If entry_id looks like a path, extract just the filename stem
        entry_path = Path(entry_id)
        pure_id = entry_path.stem if entry_path.suffix == '.json' else entry_id

        # Search for the entry file in all month subdirectories
        def _find_entry():
            for month_dir in self.dir.iterdir():
                if month_dir.is_dir():
                    entry_file = month_dir / f"{pure_id}.json"
                    if entry_file.exists():
                        return entry_file
            return None

        filepath = await asyncio.to_thread(_find_entry)
        if not filepath:
            return None

        try:
            text = await asyncio.to_thread(filepath.read_text)
            data = json.loads(text)
            return HistoryEntry.model_validate(data)
        except (json.JSONDecodeError, KeyError):
            return None

    async def clear(self) -> int:
        """Clear all history. Returns count deleted."""
        if not self.dir.exists():
            return 0

        def _do_clear() -> int:
            count = 0
            for f in self.dir.rglob("*.json"):
                f.unlink()
                count += 1
            for d in sorted(self.dir.iterdir(), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
            return count

        count = await asyncio.to_thread(_do_clear)
        logger.info(f"History cleared: {count} entries deleted")
        return count
