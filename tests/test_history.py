"""Tests for SearchHistory."""

import json
import pytest
import tempfile
from pathlib import Path

from sg.core.history import SearchHistory
from sg.models.config import HistoryConfig
from sg.models.search import SearchRequest, SearchResponse, SearchResult


@pytest.fixture
def history_dir(tmp_path):
    return str(tmp_path / "history")


@pytest.fixture
def history(history_dir):
    config = HistoryConfig(enabled=True, dir=history_dir)
    return SearchHistory(config)


@pytest.fixture
def sample_request():
    return SearchRequest(query="test query", max_results=5)


@pytest.fixture
def sample_response():
    return SearchResponse(
        query="test query",
        provider="duckduckgo",
        results=[
            SearchResult(title="Result 1", url="https://example.com/1", content="Content 1", source="duckduckgo"),
            SearchResult(title="Result 2", url="https://example.com/2", content="Content 2", source="duckduckgo"),
        ],
        total=2,
        latency_ms=150.0,
    )


class TestSearchHistory:

    @pytest.mark.asyncio
    async def test_record_and_list(self, history, sample_request, sample_response):
        """Record a search and list it."""
        entry_id = await history.record(sample_request, sample_response)
        assert entry_id is not None

        entries = await history.list()
        assert len(entries) == 1
        assert entries[0].query == "test query"
        assert entries[0].provider == "duckduckgo"
        assert entries[0].results is None  # list doesn't include results

    @pytest.mark.asyncio
    async def test_get_full_entry(self, history, sample_request, sample_response):
        """Get full entry with results."""
        entry_id = await history.record(sample_request, sample_response)
        entry = await history.get(entry_id)

        assert entry is not None
        assert entry.query == "test query"
        assert entry.results is not None
        assert len(entry.results) == 2
        assert entry.results[0].title == "Result 1"

    @pytest.mark.asyncio
    async def test_list_pagination(self, history, sample_request, sample_response):
        """Test list with limit and offset."""
        for _ in range(5):
            await history.record(sample_request, sample_response)

        all_entries = await history.list(limit=10)
        assert len(all_entries) == 5

        limited = await history.list(limit=2)
        assert len(limited) == 2

        offset = await history.list(limit=2, offset=3)
        assert len(offset) == 2

    @pytest.mark.asyncio
    async def test_clear(self, history, sample_request, sample_response):
        """Test clearing history."""
        await history.record(sample_request, sample_response)
        await history.record(sample_request, sample_response)

        count = await history.clear()
        assert count == 2

        entries = await history.list()
        assert len(entries) == 0

    @pytest.mark.asyncio
    async def test_disabled_history(self, history_dir):
        """Disabled history doesn't record."""
        config = HistoryConfig(enabled=False, dir=history_dir)
        history = SearchHistory(config)

        req = SearchRequest(query="test")
        resp = SearchResponse(query="test", provider="test", results=[], total=0, latency_ms=0)
        result = await history.record(req, resp)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, history):
        """Get nonexistent entry returns None."""
        result = await history.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_empty(self, history):
        """Clear empty history returns 0."""
        count = await history.clear()
        assert count == 0
