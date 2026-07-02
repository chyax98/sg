"""Tests for structured agent-facing output helpers."""

from sg._agent_output import format_extract_output, format_research_output, format_search_output


def test_format_search_output_inlines_all():
    result = format_search_output(
        {
            "query": "test query",
            "result_file": "/tmp/search.txt",
            "provider": "duckduckgo",
            "results": [
                {
                    "title": "Result",
                    "url": "https://example.com",
                    "score": 0.9,
                    "content": "snippet body here",
                }
            ],
            "total": 1,
        }
    )

    assert "snippet body here" in result
    assert "file:" not in result
    assert "archive:" not in result
    assert "next: read_file" not in result


def test_format_search_output_mcp_note():
    result = format_search_output(
        {
            "query": "q",
            "results": [{"title": "T", "url": "https://a.com", "content": "x"}],
            "total": 1,
        },
        for_mcp=True,
    )
    assert "Do not call extract" in result


def test_format_extract_output_inlines_content():
    result = format_extract_output(
        {
            "provider": "jina",
            "results": [
                {"url": "https://ok.example", "title": "OK", "content": "page body"},
                {"url": "https://bad.example", "error": "timeout"},
            ],
        }
    )

    assert "page body" in result
    assert "timeout" in result
    assert "next: read_file" not in result


def test_format_research_output_full_inline():
    result = format_research_output(
        {
            "topic": "AI trends",
            "result_file": "/tmp/research.txt",
            "content": "Hello world",
        }
    )

    assert "Hello world" in result
    assert "archive:" not in result
    assert "truncated" not in result