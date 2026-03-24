"""Tests for SearchHistory with JSONL view format."""

import json

import pytest

from sg.core.history import SearchHistory, _format_view_content, _parse_view_content
from sg.models.config import HistoryConfig
from sg.models.search import SearchRequest, SearchResponse, SearchResult


@pytest.fixture
def history_dir(tmp_path):
    return str(tmp_path / "history")


@pytest.fixture
def history(history_dir):
    config = HistoryConfig(dir=history_dir)
    return SearchHistory(config)


@pytest.fixture
def sample_response():
    return SearchResponse(
        query="test query",
        provider="duckduckgo",
        results=[
            SearchResult(
                title="Result 1",
                url="https://example.com/1",
                content="Content 1",
                source="duckduckgo",
            ),
            SearchResult(
                title="Result 2",
                url="https://example.com/2",
                content="Content 2\nLine 2",
                source="duckduckgo",
            ),
        ],
        total=2,
        latency_ms=150.0,
    )


class TestViewFormat:
    """Tests for JSONL view format."""

    def test_format_as_jsonl(self, sample_response):
        """View should be JSONL format - one JSON object per line."""
        content = _format_view_content(sample_response)
        lines = content.strip().split("\n")

        # Each line should be valid JSON
        assert len(lines) == 2
        data1 = json.loads(lines[0])
        data2 = json.loads(lines[1])

        assert data1["index"] == 1
        assert data1["title"] == "Result 1"
        assert data1["url"] == "https://example.com/1"
        assert data1["content"] == "Content 1"

        assert data2["index"] == 2
        assert data2["content"] == "Content 2\nLine 2"  # Newlines preserved in JSON

    def test_parse_jsonl_roundtrip(self, sample_response):
        """JSONL should be reversible."""
        content = _format_view_content(sample_response)
        results = _parse_view_content(content, "duckduckgo")

        assert len(results) == 2
        assert results[0].title == "Result 1"
        assert results[0].content == "Content 1"
        assert results[1].title == "Result 2"
        assert results[1].content == "Content 2\nLine 2"

    def test_line_oriented_format(self, sample_response):
        """Each result is on its own line - supports line-level reading."""
        content = _format_view_content(sample_response)

        # Line 1 = result [1], Line 2 = result [2]
        lines = content.strip().split("\n")
        assert len(lines) == 2

        # Can read specific line to get specific result
        line1_data = json.loads(lines[0])
        assert line1_data["index"] == 1

        line2_data = json.loads(lines[1])
        assert line2_data["index"] == 2


class TestSearchHistory:
    """Tests for SearchHistory."""

    @pytest.mark.asyncio
    async def test_record_creates_jsonl_view(self, history, sample_response):
        req = SearchRequest(query="test", max_results=5)
        view_file = await history.record(req, sample_response)

        # View file should be JSONL
        view_path = history.view_dir / "2026-03" / view_file.split("/")[-1]
        content = view_path.read_text()

        # Each line is valid JSON
        for line in content.strip().split("\n"):
            data = json.loads(line)
            assert "index" in data
            assert "title" in data
            assert "url" in data
            assert "content" in data

    @pytest.mark.asyncio
    async def test_get_reads_from_jsonl(self, history, sample_response):
        req = SearchRequest(query="test", max_results=5)
        view_file = await history.record(req, sample_response)
        entry_id = view_file.split("/")[-1].replace(".txt", "")

        entry = await history.get(entry_id)

        assert entry is not None
        assert len(entry.results) == 2
        assert entry.results[0].title == "Result 1"
        assert entry.results[1].title == "Result 2"

    @pytest.mark.asyncio
    async def test_selective_read_by_line(self, history, sample_response):
        """Simulate AI reading only line 2 (result [2])."""
        req = SearchRequest(query="test", max_results=5)
        view_file = await history.record(req, sample_response)

        view_path = history.view_dir / "2026-03" / view_file.split("/")[-1]
        lines = view_path.read_text().strip().split("\n")

        # AI wants only result [2] - read line 2
        line2 = lines[1]  # 0-indexed, so line 2 is index 1
        data = json.loads(line2)

        assert data["index"] == 2
        assert data["title"] == "Result 2"
