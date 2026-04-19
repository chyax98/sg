"""Tests for structured agent-facing output helpers."""

from sg._agent_output import format_extract_output, format_research_output, format_search_output


def test_format_search_output_includes_file_and_next_step():
    result = format_search_output(
        {
            "query": "test query",
            "result_file": "/tmp/search.txt",
            "results": [{"title": "Result", "url": "https://example.com", "score": 0.9}],
            "total": 1,
        }
    )

    assert "type: search" in result
    assert "file: /tmp/search.txt" in result
    assert "next: read_file" in result
    assert "preview[1]{line,title,url,score}:" in result


def test_format_extract_output_separates_files_and_errors():
    result = format_extract_output(
        {
            "result_files": [
                {
                    "url": "https://ok.example",
                    "file": "/tmp/extract.txt",
                    "chars": 120,
                    "lines": 5,
                    "title": "OK",
                },
                {
                    "url": "https://bad.example",
                    "error": "timeout",
                },
            ]
        }
    )

    assert "type: extract" in result
    assert "files[1]{idx,file,chars,lines,title}:" in result
    assert "errors[1]{idx,url,error}:" in result
    assert "next: read_file" in result


def test_format_research_output_includes_preview_and_file():
    result = format_research_output(
        {
            "topic": "AI trends",
            "result_file": "/tmp/research.txt",
            "content": "Hello world",
        }
    )

    assert "type: research" in result
    assert "topic: AI trends" in result
    assert "file: /tmp/research.txt" in result
    assert "preview:" in result
