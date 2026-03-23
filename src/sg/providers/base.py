"""Provider base classes with self-describing metadata."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)


class ProviderCapabilityError(ValueError):
    """Raised when a provider cannot satisfy requested search semantics."""


@dataclass(frozen=True)
class ProviderInfo:
    """Provider type metadata — declared once per provider class."""
    type: str
    display_name: str
    needs_api_key: bool = True
    needs_url: bool = False
    free: bool = False
    capabilities: tuple[str, ...] = ("search",)
    search_features: tuple[str, ...] = ()


class BaseProvider(ABC):
    """Base class for all providers."""

    info: ClassVar[ProviderInfo]

    def __init__(self, name: str, *, api_key: str | None = None,
                 url: str | None = None, priority: int = 10,
                 timeout: int = 30000, **kwargs):
        self.name = name
        self.api_key = api_key
        self.url = url
        self.priority = priority
        self.timeout = timeout

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider. Returns True if ready."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources."""
        ...

    async def health_check(self) -> tuple[bool, str | None]:
        """Lightweight health check. Override for active probing."""
        return (True, None)

    @property
    def capabilities(self) -> list[str]:
        return list(self.info.capabilities)


class SearchProvider(BaseProvider):
    """Provider with search capability."""

    @property
    def search_features(self) -> list[str]:
        return list(self.info.search_features)

    def validate_search_request(self, request: SearchRequest) -> None:
        """Reject search parameters a provider does not support."""
        features = set(self.info.search_features)
        unsupported: list[str] = []

        if request.include_domains and "include_domains" not in features:
            unsupported.append("include_domains")
        if request.exclude_domains and "exclude_domains" not in features:
            unsupported.append("exclude_domains")
        if request.time_range and "time_range" not in features:
            unsupported.append("time_range")
        if request.search_depth != "basic" and "search_depth" not in features:
            unsupported.append("search_depth")

        if unsupported:
            joined = ", ".join(unsupported)
            raise ProviderCapabilityError(
                f"{self.name} does not support search params: {joined}"
            )

    @staticmethod
    def apply_domain_operators(
        query: str,
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> str:
        """Apply site operators to providers that support query syntax filtering."""
        for domain in include_domains:
            query += f" site:{domain}"
        for domain in exclude_domains:
            query += f" -site:{domain}"
        return query

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        ...


class ExtractProvider(BaseProvider):
    """Provider with extract capability."""

    @abstractmethod
    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        ...


class ResearchProvider(BaseProvider):
    """Provider with research capability."""

    @abstractmethod
    async def research(self, request: ResearchRequest) -> ResearchResponse:
        ...
