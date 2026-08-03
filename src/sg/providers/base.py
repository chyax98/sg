"""Provider base classes — adapters over the standard protocol."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from ..models.search import (
    ExtractCapability,
    ExtractRequest,
    ExtractResponse,
    ProviderCapability,
    ResearchCapability,
    ResearchRequest,
    ResearchResponse,
    SearchCapability,
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
    # Structured protocol capability (source of truth)
    capability: ProviderCapability = field(default_factory=ProviderCapability)
    # Legacy flat lists kept for older API clients
    capabilities: tuple[str, ...] = ()
    search_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Derive flat lists from structured capability only.
        if not self.capabilities:
            object.__setattr__(self, "capabilities", tuple(self.capability.ops))
        if not self.search_features and self.capability.search is not None:
            sc = self.capability.search
            feats: list[str] = []
            if sc.domains:
                feats.append("domains")
            if sc.exclude_domains:
                feats.append("exclude_domains")
            if sc.time_range:
                feats.append("time_range")
            if sc.depth:
                feats.append("depth")
            if sc.language:
                feats.append("language")
            if sc.location:
                feats.append("location")
            if sc.raw_content:
                feats.append("raw_content")
            object.__setattr__(self, "search_features", tuple(feats))
        # If only legacy tuples were provided, build capability once.
        if not self.capability.ops and self.capabilities:
            feats_set: set[str] = set(self.search_features)
            search = (
                SearchCapability(
                    domains="domains" in feats_set,
                    exclude_domains="exclude_domains" in feats_set,
                    time_range="time_range" in feats_set,
                    depth="depth" in feats_set,
                    language="language" in feats_set,
                    location="location" in feats_set,
                    raw_content="raw_content" in feats_set,
                )
                if "search" in self.capabilities
                else None
            )
            extract = ExtractCapability() if "extract" in self.capabilities else None
            research = ResearchCapability() if "research" in self.capabilities else None
            object.__setattr__(
                self,
                "capability",
                ProviderCapability(search=search, extract=extract, research=research),
            )


def search_cap(**kwargs: bool) -> SearchCapability:
    return SearchCapability(**kwargs)


def extract_cap(
    formats: tuple[str, ...] = ("markdown",),
    multi_url: bool = True,
    only_main: bool = False,
) -> ExtractCapability:
    return ExtractCapability(formats=list(formats), multi_url=multi_url, only_main=only_main)  # type: ignore[arg-type]


def research_cap(depths: tuple[str, ...] = ("auto", "mini", "pro")) -> ResearchCapability:
    return ResearchCapability(depths=list(depths))  # type: ignore[arg-type]


def cap(
    *,
    search: SearchCapability | None = None,
    extract: ExtractCapability | None = None,
    research: ResearchCapability | None = None,
) -> ProviderCapability:
    return ProviderCapability(search=search, extract=extract, research=research)


class BaseProvider(ABC):
    """Base adapter."""

    info: ClassVar[ProviderInfo]

    def __init__(
        self,
        name: str,
        *,
        api_key: str | None = None,
        url: str | None = None,
        priority: int = 10,
        timeout: int = 30000,
        env: dict[str, str] | None = None,
        **kwargs,
    ):
        self.name = name
        self.api_key = api_key
        self.url = url
        self.priority = priority
        self.timeout = timeout
        self.env = env or {}

    def env_value(self, name: str) -> str | None:
        return self.env.get(name) or os.environ.get(name)

    @abstractmethod
    async def initialize(self) -> bool: ...

    @abstractmethod
    async def shutdown(self) -> None: ...

    async def health_check(self) -> tuple[bool, str | None]:
        return (True, None)

    @property
    def capabilities(self) -> list[str]:
        return list(self.info.capability.ops or self.info.capabilities)

    @property
    def protocol_capability(self) -> ProviderCapability:
        return self.info.capability


class SearchProvider(BaseProvider):
    """Adapter with search."""

    @property
    def search_features(self) -> list[str]:
        return list(self.info.search_features)

    def validate_search_request(self, request: SearchRequest) -> None:
        """Hard-fail on unsupported params (after Gateway projection, should be rare)."""
        sc = self.info.capability.search
        if sc is None:
            raise ProviderCapabilityError(f"{self.name} does not support search")
        unsupported: list[str] = []
        if request.domains and not sc.domains:
            unsupported.append("domains")
        if request.exclude_domains and not sc.exclude_domains:
            unsupported.append("exclude_domains")
        if request.time_range and not sc.time_range:
            unsupported.append("time_range")
        if request.depth != "basic" and not sc.depth:
            unsupported.append("depth")
        if request.language and not sc.language:
            unsupported.append("language")
        if request.location and not sc.location:
            unsupported.append("location")
        if request.want_raw and not sc.raw_content:
            unsupported.append("want_raw")
        if unsupported:
            raise ProviderCapabilityError(
                f"{self.name} does not support search params: {', '.join(unsupported)}"
            )

    @staticmethod
    def apply_domain_operators(
        query: str,
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> str:
        for domain in include_domains:
            query += f" site:{domain}"
        for domain in exclude_domains:
            query += f" -site:{domain}"
        return query

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse: ...


class ExtractProvider(BaseProvider):
    @abstractmethod
    async def extract(self, request: ExtractRequest) -> ExtractResponse: ...


class ResearchProvider(BaseProvider):
    @abstractmethod
    async def research(self, request: ResearchRequest) -> ResearchResponse: ...
