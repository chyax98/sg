"""Tests for agent-facing output helpers."""

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
                    "snippet": "snippet body here",
                }
            ],
            "total": 1,
        }
    )

    assert "snippet body here" in result
    assert "https://example.com" in result
    assert "provider" not in result.lower()
    assert "file:" not in result
    assert "duckduckgo" not in result


def test_format_search_empty():
    assert format_search_output({"results": []}) == "No results."


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
    assert "jina" not in result
    assert "provider" not in result.lower()


def test_format_research_output_full_inline():
    result = format_research_output(
        {
            "topic": "AI trends",
            "provider": "tavily",
            "report": "Hello world",
            "sources": ["https://a.example", "https://b.example"],
        }
    )

    assert "Hello world" in result
    assert "AI trends" in result
    assert "https://a.example" in result
    assert "tavily" not in result


def test_format_research_output_surfaces_degrade_notice():
    result = format_research_output(
        {
            "topic": "AI UI",
            "provider": "search:exa-1",
            "report": "Brief from hits",
            "sources": ["https://a.example"],
            "degraded": True,
            "notice": "research unavailable; degraded to search summary",
        }
    )

    assert "degraded to search summary" in result
    assert "Brief from hits" in result
    assert result.index("degraded") < result.index("Brief from hits")
