"""Tests for SearchHistory — focused on real-world scenarios.

Key concerns:
- Content integrity: does wrapping lose or corrupt data?
- AI readability: can an AI agent use line ranges to navigate large files?
- Concurrency: do parallel record_extract calls produce correct, separate files?
- Real markdown: code blocks, tables, and URLs must survive wrapping intact.
"""

import asyncio
import json
from pathlib import Path

import pytest

from sg.core.history import SearchHistory, _format_view_content, _parse_view_content, _wrap_content
from sg.models.config import HistoryConfig
from sg.models.search import ExtractResult, SearchRequest, SearchResponse, SearchResult


@pytest.fixture
def history(tmp_path):
    config = HistoryConfig(dir=str(tmp_path / "history"))
    return SearchHistory(config)


# ============================================================
# Realistic test content
# ============================================================

# Simulates a real extracted web page (~100k chars)
_LARGE_MARKDOWN = (
    "# Gemini CLI Configuration Guide\n\n"
    + "This is a comprehensive guide to configuring the Gemini CLI. " * 200 + "\n\n"  # ~12k chars
    + "## Installation\n\n"
    + "```bash\npip install gemini-cli\nexport GEMINI_API_KEY=\"your-key-here\"\ngemini --version\n```\n\n"
    + "## Configuration Layers\n\n"
    + "| Layer | Location | Precedence |\n"
    + "| --- | --- | --- |\n"
    + "| System defaults | `/etc/gemini-cli/settings.json` | 1 (lowest) |\n"
    + "| User settings | `~/.gemini/settings.json` | 2 |\n"
    + "| Project settings | `.gemini/settings.json` | 3 |\n"
    + "| Environment variables | `$GEMINI_API_KEY`, `$GEMINI_MODEL` | 4 |\n"
    + "| CLI arguments | `--model`, `--sandbox` | 5 (highest) |\n\n"
    + "## Environment Variables\n\n"
    + "The following environment variables are supported:\n\n"
    + "- `GEMINI_API_KEY`: Your API key for authentication. This is required for all operations. "
      "Without this key, the CLI will fail to initialize and display an error message. " * 20 + "\n"
    + "- `GEMINI_MODEL`: Override the default model. Accepts values like `gemini-2.5-pro`, `gemini-2.5-flash`. "
      "When set, this takes precedence over any model specified in settings.json files. " * 20 + "\n\n"
    + "## MCP Server Configuration\n\n"
    + '```json\n{\n  "mcpServers": {\n    "sg": {\n      "command": "uv",\n'
    + '      "args": ["run", "--directory", "/path/to/search-gateway", "sg", "mcp"],\n'
    + '      "env": {"SG_PORT": "8100"}\n    }\n  }\n}\n```\n\n'
    + "## Advanced Settings\n\n"
    + "For advanced users, the following settings are available in `settings.json`:\n\n"
    + ("- `advanced.dnsResolutionOrder`: Controls DNS resolution order for network requests. "
       "This can be useful when running in environments with specific DNS requirements. "
       "Accepts 'ipv4', 'ipv6', or 'auto'. Default is 'auto'. " * 5 + "\n") * 10
)

_LONG_URL = "https://github.com/google-gemini/gemini-cli/blob/main/packages/cli/src/config/extensions/variables.ts#L17-L40"


# ============================================================
# _wrap_content: content integrity on real data
# ============================================================

class TestWrapContentIntegrity:
    """Does wrapping preserve ALL content? This is the #1 concern."""

    def test_large_markdown_no_data_loss(self):
        """After wrapping, joining all lines with spaces should recover original words."""
        original = _LARGE_MARKDOWN
        wrapped = _wrap_content(original)

        # Every word in the original must appear in the wrapped output
        original_words = set(original.split())
        wrapped_words = set(wrapped.split())

        missing = original_words - wrapped_words
        assert not missing, f"Words lost during wrapping: {missing}"

    def test_code_blocks_not_broken(self):
        """Code blocks should remain intact — breaking inside them corrupts code."""
        code = "```python\ndef hello():\n    print('world')\n    return 42\n```"
        result = _wrap_content(code)

        # Each line of the code block should be preserved exactly
        assert "def hello():" in result
        assert "    print('world')" in result
        assert "    return 42" in result

    def test_long_url_stays_on_one_line(self):
        """URLs should never be broken — a split URL is useless."""
        text = f"See the documentation at {_LONG_URL} for details."
        result = _wrap_content(text)

        # The URL must appear intact somewhere in the output
        assert _LONG_URL in result

    def test_table_rows_may_wrap_but_content_preserved(self):
        """Markdown tables have long lines. Content must survive even if lines wrap."""
        table = (
            "| Setting | Description | Default |\n"
            "| --- | --- | --- |\n"
            "| `model.name` | The model to use for generation. Accepts any valid Gemini model identifier. | `gemini-2.5-flash` |\n"
        )
        result = _wrap_content(table)

        # All cell values must be present
        assert "`model.name`" in result
        assert "`gemini-2.5-flash`" in result
        assert "The model to use for generation" in result

    def test_all_lines_within_limit(self):
        """No line should exceed the width limit (with tolerance for unbreakable tokens)."""
        wrapped = _wrap_content(_LARGE_MARKDOWN)
        for i, line in enumerate(wrapped.split("\n"), 1):
            # Allow lines with unbreakable tokens (URLs, code) to exceed slightly
            if len(line) > 220 and " " in line:
                pytest.fail(f"Line {i} is {len(line)} chars and has spaces (should have wrapped): {line[:80]}...")

    def test_empty_and_whitespace_preserved(self):
        """Blank lines in markdown are paragraph separators — must not be collapsed."""
        text = "paragraph 1\n\n\nparagraph 2"
        result = _wrap_content(text)
        assert "\n\n\n" in result


# ============================================================
# record_extract: real-world file format for AI consumption
# ============================================================

class TestRecordExtractRealWorld:
    """Test that files produced by record_extract are actually useful for AI agents."""

    @pytest.mark.asyncio
    async def test_large_page_produces_navigable_file(self, history):
        """A 100k char page should produce a file where AI can read sections."""
        result = ExtractResult(
            url="https://docs.example.com/gemini-cli/configuration",
            content=_LARGE_MARKDOWN,
            title="Gemini CLI Configuration Guide",
        )

        manifest = await history.record_extract(
            urls=[result.url],
            results=[result],
            provider="exa",
            latency_ms=1500.0,
        )

        assert len(manifest) == 1
        entry = manifest[0]

        # File must exist
        file_path = Path(entry["file"])
        assert file_path.exists()

        all_lines = file_path.read_text().split("\n")
        total_lines = len(all_lines)

        # File should have many lines (not a single giant line!)
        assert total_lines > 50, f"Only {total_lines} lines for {len(_LARGE_MARKDOWN)} chars — not enough granularity"

        # HEADER: first 3 lines = URL, Title, separator
        assert all_lines[0] == "URL: https://docs.example.com/gemini-cli/configuration"
        assert all_lines[1] == "Title: Gemini CLI Configuration Guide"
        assert all_lines[2] == "---"

        # BODY starts at line 4 (index 3)
        first_chunk = "\n".join(all_lines[3:53])
        assert len(first_chunk) > 0
        assert len(first_chunk) < len(_LARGE_MARKDOWN), "First chunk should be a subset"

        # AI reads next 50 lines
        second_chunk = "\n".join(all_lines[53:103])
        assert len(second_chunk) > 0
        assert first_chunk != second_chunk

        # INTEGRITY: all content must be in the file
        full_body = "\n".join(all_lines[3:])
        for keyword in ["Configuration Layers", "Environment Variables", "MCP Server", "Advanced Settings"]:
            assert keyword in full_body, f"Section '{keyword}' missing from file"

    @pytest.mark.asyncio
    async def test_manifest_chars_matches_original(self, history):
        """manifest[chars] should report the ORIGINAL content length, not wrapped length."""
        content = "x" * 50000
        result = ExtractResult(url="https://x.com", content=content, title="Big")

        manifest = await history.record_extract(
            urls=["https://x.com"],
            results=[result],
            provider="exa",
            latency_ms=100.0,
        )

        assert manifest[0]["chars"] == 50000

    @pytest.mark.asyncio
    async def test_error_url_doesnt_create_garbage_file(self, history):
        """Error results should be small, not a full content file."""
        results = [
            ExtractResult(url="https://ok.com", content="Good content " * 100, title="OK"),
            ExtractResult(url="https://timeout.com", content="", error="Connection timeout after 30s"),
        ]

        manifest = await history.record_extract(
            urls=["https://ok.com", "https://timeout.com"],
            results=results,
            provider="exa,jina",
            latency_ms=30000.0,
        )

        # OK file should have real content
        ok_file = Path(manifest[0]["file"])
        assert ok_file.stat().st_size > 100

        # Error file should be tiny (just URL + error message)
        err_file = Path(manifest[1]["file"])
        err_content = err_file.read_text()
        assert "Connection timeout" in err_content
        assert len(err_content) < 200


# ============================================================
# Concurrent record_extract: the real danger zone
# ============================================================

class TestRecordExtractConcurrency:
    """Multiple extract requests hitting record_extract simultaneously."""

    @pytest.mark.asyncio
    async def test_parallel_extracts_produce_separate_files(self, history):
        """3 concurrent extract calls should produce 3 separate, correct files."""

        async def do_extract(url: str, content: str):
            return await history.record_extract(
                urls=[url],
                results=[ExtractResult(url=url, content=content, title=f"Page {url}")],
                provider="exa",
                latency_ms=100.0,
            )

        # Fire 3 extracts concurrently
        m1, m2, m3 = await asyncio.gather(
            do_extract("https://a.com", "Content A " * 500),
            do_extract("https://b.com", "Content B " * 500),
            do_extract("https://c.com", "Content C " * 500),
        )

        # Each should produce exactly 1 file
        assert len(m1) == 1 and len(m2) == 1 and len(m3) == 1

        # Files must be different
        files = {m1[0]["file"], m2[0]["file"], m3[0]["file"]}
        assert len(files) == 3, f"File collision: {files}"

        # Each file must contain ONLY its own content (no cross-contamination)
        assert "Content A" in Path(m1[0]["file"]).read_text()
        assert "Content B" in Path(m2[0]["file"]).read_text()
        assert "Content C" in Path(m3[0]["file"]).read_text()

        assert "Content B" not in Path(m1[0]["file"]).read_text()  # no cross-contamination

    @pytest.mark.asyncio
    async def test_parallel_multi_url_extracts(self, history):
        """Concurrent multi-URL extracts (each with 3 URLs) must not corrupt."""

        async def batch_extract(prefix: str):
            urls = [f"https://{prefix}{i}.com" for i in range(3)]
            results = [
                ExtractResult(url=u, content=f"Content-{prefix}{i} " * 200, title=f"P-{prefix}{i}")
                for i, u in enumerate(urls)
            ]
            return await history.record_extract(urls=urls, results=results, provider="jina", latency_ms=200.0)

        m_a, m_b = await asyncio.gather(
            batch_extract("a"),
            batch_extract("b"),
        )

        # Each batch should produce 3 files
        assert len(m_a) == 3
        assert len(m_b) == 3

        # All 6 files should be unique
        all_files = {e["file"] for e in m_a + m_b}
        assert len(all_files) == 6

        # Spot check content integrity
        assert "Content-a0" in Path(m_a[0]["file"]).read_text()
        assert "Content-b2" in Path(m_b[2]["file"]).read_text()


# ============================================================
# Search JSONL format (existing, kept for regression)
# ============================================================

class TestSearchJSONL:
    def test_format_roundtrip(self):
        response = SearchResponse(
            query="test",
            provider="exa",
            results=[
                SearchResult(title="R1", url="https://a.com", content="C1\nLine2", source="exa", score=0.95),
                SearchResult(title="R2", url="https://b.com", content="C2", source="exa"),
            ],
            total=2,
            latency_ms=100.0,
        )

        jsonl = _format_view_content(response)
        parsed = _parse_view_content(jsonl, "exa")

        assert len(parsed) == 2
        assert parsed[0].title == "R1"
        assert parsed[0].content == "C1\nLine2"  # newlines preserved
        assert parsed[0].score == 0.95
        assert parsed[1].title == "R2"

    @pytest.mark.asyncio
    async def test_record_and_get_roundtrip(self, history):
        """Full cycle: record → list → get → verify results match."""
        response = SearchResponse(
            query="gemini cli config",
            provider="exa",
            results=[
                SearchResult(title="Config Guide", url="https://docs.com/config", content="Config docs...", source="exa"),
            ],
            total=1,
            latency_ms=200.0,
        )
        req = SearchRequest(query="gemini cli config")

        view_file = await history.record(req, response)
        assert Path(view_file).exists()

        entries = await history.list()
        assert len(entries) == 1
        assert entries[0].query == "gemini cli config"

        full = await history.get(entries[0].id)
        assert full is not None
        assert len(full.results) == 1
        assert full.results[0].title == "Config Guide"
        assert full.results[0].content == "Config docs..."

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, history):
        response = SearchResponse(
            query="test", provider="exa",
            results=[SearchResult(title="R", url="https://x.com", content="c", source="exa")],
            total=1, latency_ms=10.0,
        )
        await history.record(SearchRequest(query="test"), response)
        await history.record(SearchRequest(query="test2"), response)

        deleted = await history.clear()
        assert deleted >= 4  # 2 view + 2 trace files

        entries = await history.list()
        assert len(entries) == 0


# ============================================================
# record_content (research) — wrapped plain text
# ============================================================

class TestRecordContent:
    @pytest.mark.asyncio
    async def test_research_content_is_readable_not_json(self, history):
        """Research content should be stored as readable text, not a JSON blob."""
        content = (
            "# AI Trends 2026\n\n"
            "Artificial intelligence continues to evolve rapidly. " * 100 + "\n\n"
            "## Key Findings\n\n"
            "1. LLM costs have dropped 90% year over year\n"
            "2. Agent frameworks are converging on tool-use patterns\n"
            "3. Multimodal models are becoming the default\n"
        )

        view_file = await history.record_content(
            operation="research",
            query="AI trends 2026",
            provider="tavily",
            latency_ms=15000.0,
            content=content,
        )

        text = Path(view_file).read_text()

        # Must NOT be JSON
        assert not text.startswith("{")
        assert not text.startswith("[")

        # Must be readable plain text with reasonable line lengths
        max_line_len = max(len(line) for line in text.split("\n"))
        assert max_line_len <= 220

        # Content integrity
        assert "# AI Trends 2026" in text
        assert "## Key Findings" in text
        assert "LLM costs have dropped 90%" in text
