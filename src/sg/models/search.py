"""Standard search protocol — single schema for HTTP / MCP / adapters."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TimeRange = Literal["day", "week", "month", "year"]
SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]
ExtractFormat = Literal["markdown", "text", "html"]
ResearchDepth = Literal["auto", "mini", "pro"]


class SearchCapability(BaseModel):
    domains: bool = False
    exclude_domains: bool = False
    time_range: bool = False
    depth: bool = False
    language: bool = False
    location: bool = False
    raw_content: bool = False


class ExtractCapability(BaseModel):
    formats: list[ExtractFormat] = Field(default=["markdown"])
    multi_url: bool = True
    only_main: bool = False


class ResearchCapability(BaseModel):
    depths: list[ResearchDepth] = Field(default=["auto", "mini", "pro"])


class ProviderCapability(BaseModel):
    search: SearchCapability | None = None
    extract: ExtractCapability | None = None
    research: ResearchCapability | None = None

    @property
    def ops(self) -> list[str]:
        out: list[str] = []
        if self.search is not None:
            out.append("search")
        if self.extract is not None:
            out.append("extract")
        if self.research is not None:
            out.append("research")
        return out


class SearchRequest(BaseModel):
    query: str
    provider: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    depth: SearchDepth = "basic"
    language: str | None = None
    location: str | None = None
    want_raw: bool = False

    @field_validator("domains", "exclude_domains", mode="before")
    @classmethod
    def _clean_str_list(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if str(x).strip()]


class ExtractRequest(BaseModel):
    urls: list[str]
    format: ExtractFormat = "markdown"
    only_main: bool | None = None
    provider: str | None = None

    @field_validator("urls", mode="before")
    @classmethod
    def _clean_urls(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [v]
        urls = [str(u).strip() for u in (v or []) if str(u).strip()]
        if not urls:
            raise ValueError("urls must be non-empty")
        return urls


class ResearchRequest(BaseModel):
    topic: str
    depth: ResearchDepth = "auto"
    provider: str | None = None


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = ""
    score: float = 0.0
    source: str = ""
    published_at: str | None = None
    author: str | None = None
    raw: str | None = None


# Keep name SearchResult for less churn in history/tests; shape is the hit protocol.
SearchResult = SearchHit


class SearchResponse(BaseModel):
    query: str
    provider: str
    results: list[SearchHit] = Field(default_factory=list)
    total: int = 0
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    result_file: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _total(self) -> SearchResponse:
        if not self.total:
            self.total = len(self.results)
        return self


class ExtractPage(BaseModel):
    url: str
    content: str = ""
    title: str | None = None
    error: str | None = None


ExtractResult = ExtractPage


class ExtractResponse(BaseModel):
    results: list[ExtractPage] = Field(default_factory=list)
    provider: str
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    result_files: list[dict] | None = None


class ResearchResponse(BaseModel):
    topic: str
    report: str
    sources: list[str] = Field(default_factory=list)
    provider: str
    latency_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    result_file: str | None = None


# --- Context7 docs side-path (not web search) ---


class DocsLibrarySearchRequest(BaseModel):
    """resolve-library-id: libraryName + query (both required by Context7 API)."""

    library_name: str
    query: str
    fast: bool = False


class DocsLibraryHit(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    stars: int | None = None
    trust_score: float | None = None
    benchmark_score: float | None = None
    total_snippets: int | None = None
    versions: list[str] = Field(default_factory=list)
    state: str = ""


class DocsLibrarySearchResponse(BaseModel):
    library_name: str
    query: str = ""
    results: list[DocsLibraryHit] = Field(default_factory=list)
    provider: str = ""
    latency_ms: float = 0.0
    error: str | None = None


class DocsContextRequest(BaseModel):
    """query-docs: libraryId + query."""

    library_id: str
    query: str
    fast: bool = False


class DocsContextResponse(BaseModel):
    library_id: str
    query: str
    content: str = ""
    provider: str = ""
    latency_ms: float = 0.0


class ProviderStatus(BaseModel):
    name: str
    group: str = ""
    type: str = ""
    enabled: bool
    healthy: bool
    capabilities: list[str]
    search_features: list[str] = Field(default_factory=list)
    capability: ProviderCapability | None = None
    priority: int
    fallback_for: list[str] = Field(default_factory=list)
    circuit_breaker: str = "closed"
    latency_ms: float | None = None
    error: str | None = None


class HistoryEntry(BaseModel):
    id: str
    query: str
    provider: str
    total: int
    latency_ms: float
    timestamp: str
    operation: str = "search"
    results: list[SearchHit] | None = None
    files: list[dict] | None = None
    content: str | None = None
