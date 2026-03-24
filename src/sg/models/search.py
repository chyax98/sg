"""Search request/response models."""

from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Search request."""

    query: str
    provider: str | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    time_range: str | None = None  # day, week, month, year
    search_depth: str = "basic"  # basic, advanced, fast, ultra-fast
    extra: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Single search result."""

    title: str
    url: str
    content: str = ""
    snippet: str = ""
    score: float = 0.0
    source: str
    published_date: str | None = None
    author: str | None = None
    raw_content: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if self.snippet and not self.content:
            self.content = self.snippet
        elif self.content and not self.snippet:
            self.snippet = self.content


class SearchResponse(BaseModel):
    """Search response."""

    query: str
    provider: str
    results: list[SearchResult]
    total: int
    latency_ms: float
    result_file: str | None = None  # path to history file, set after recording


class ExtractRequest(BaseModel):
    """Extract request."""

    urls: list[str]
    format: str = "markdown"
    extract_depth: str = "basic"
    query: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ExtractResult(BaseModel):
    """Extract result."""

    url: str
    content: str
    title: str | None = None
    error: str | None = None


class ExtractResponse(BaseModel):
    """Extract response."""

    results: list[ExtractResult]
    provider: str
    latency_ms: float
    result_file: str | None = None


class ResearchRequest(BaseModel):
    """Deep research request."""

    topic: str
    depth: str = "auto"


class ResearchResponse(BaseModel):
    """Deep research response."""

    topic: str
    content: str
    sources: list[str]
    provider: str
    latency_ms: float
    result_file: str | None = None


class ProviderStatus(BaseModel):
    """Provider status for API responses."""

    name: str
    group: str = ""
    type: str = ""
    enabled: bool
    healthy: bool
    capabilities: list[str]
    search_features: list[str] = Field(default_factory=list)
    priority: int
    fallback_for: list[str] = Field(default_factory=list)
    circuit_breaker: str = "closed"
    latency_ms: float | None = None
    error: str | None = None


class HistoryEntry(BaseModel):
    """Search history entry."""

    id: str
    query: str
    provider: str
    total: int
    latency_ms: float
    timestamp: str
    results: list[SearchResult] | None = None
