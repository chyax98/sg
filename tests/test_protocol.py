"""Standard protocol projection tests."""

from sg.models.search import ExtractRequest, ResearchRequest, SearchRequest
from sg.protocol import project_extract, project_research, project_search
from sg.providers.base import extract_cap, research_cap, search_cap
from sg.providers.tavily import TavilyProvider


def test_search_request_fields():
    req = SearchRequest(query="q", limit=7, domains=["a.com"], depth="advanced")
    assert req.limit == 7
    assert req.domains == ["a.com"]
    assert req.depth == "advanced"


def test_project_search_strips_unsupported():
    cap_s = search_cap(domains=True)
    req = SearchRequest(
        query="q", domains=["a.com"], time_range="week", depth="advanced", want_raw=True
    )
    out = project_search(req, cap_s)
    assert out.request.domains == ["a.com"]
    assert out.request.time_range is None
    assert out.request.depth == "basic"
    assert out.request.want_raw is False
    assert out.warnings


def test_project_extract_format_fallback():
    cap_e = extract_cap(formats=("markdown",), multi_url=False)
    req = ExtractRequest(urls=["https://a.com", "https://b.com"], format="html")
    out = project_extract(req, cap_e)
    assert out.request.format == "markdown"
    assert out.request.urls == ["https://a.com"]


def test_project_research_depth():
    cap_r = research_cap(depths=("auto", "mini"))
    req = ResearchRequest(topic="t", depth="pro")
    out = project_research(req, cap_r)
    assert out.request.depth in ("auto", "mini")


def test_tavily_info_capability_ops():
    assert set(TavilyProvider.info.capability.ops) == {"search", "extract", "research"}
