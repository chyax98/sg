"""Provider base classes."""

from abc import ABC, abstractmethod
from typing import Any

from ..models.search import (
    ExtractRequest,
    ExtractResponse,
    ResearchRequest,
    ResearchResponse,
    SearchRequest,
    SearchResponse,
)


class BaseProvider(ABC):
    """Base class for all providers."""

    name: str
    capabilities: list[str] = ["search"]
    is_fallback: bool = False

    def __init__(self, **kwargs):
        self.enabled = True
        self.healthy = True
        self.priority = kwargs.get("priority", 10)
        self.timeout = kwargs.get("timeout", 30000)
        self._client = None

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider. Returns True if successful."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup resources."""
        pass

    @abstractmethod
    async def health_check(self) -> tuple[bool, str | None]:
        """Check if provider is healthy. Returns (healthy, error_message)."""
        pass

    @property
    def supports_search(self) -> bool:
        return "search" in self.capabilities

    @property
    def supports_extract(self) -> bool:
        return "extract" in self.capabilities

    @property
    def supports_research(self) -> bool:
        return "research" in self.capabilities


class SearchProvider(BaseProvider):
    """Provider with search capability."""

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute search."""
        pass


class ExtractProvider(BaseProvider):
    """Provider with extract capability."""

    @abstractmethod
    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract content from URLs."""
        pass


class ResearchProvider(BaseProvider):
    """Provider with research capability."""

    @abstractmethod
    async def research(self, request: ResearchRequest) -> ResearchResponse:
        """Execute deep research."""
        pass
