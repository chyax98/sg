"""Protocol projection: strip unsupported fields by capability, attach warnings."""

from __future__ import annotations

from dataclasses import dataclass

from .models.search import (
    ExtractCapability,
    ExtractRequest,
    ProviderCapability,
    ResearchCapability,
    ResearchRequest,
    SearchCapability,
    SearchRequest,
)
from .providers.base import ProviderInfo


def capability_from_info(info: ProviderInfo) -> ProviderCapability:
    """Build ProviderCapability from ProviderInfo (single source for adapters)."""
    return info.capability


@dataclass
class ProjectedSearch:
    request: SearchRequest
    warnings: list[str]


@dataclass
class ProjectedExtract:
    request: ExtractRequest
    warnings: list[str]


@dataclass
class ProjectedResearch:
    request: ResearchRequest
    warnings: list[str]


def project_search(req: SearchRequest, cap: SearchCapability | None) -> ProjectedSearch:
    warnings: list[str] = []
    if cap is None:
        return ProjectedSearch(request=req, warnings=["provider does not support search"])

    data = req.model_dump()
    if req.domains and not cap.domains:
        data["domains"] = []
        warnings.append("stripped domains (unsupported)")
    if req.exclude_domains and not cap.exclude_domains:
        data["exclude_domains"] = []
        warnings.append("stripped exclude_domains (unsupported)")
    if req.time_range and not cap.time_range:
        data["time_range"] = None
        warnings.append("stripped time_range (unsupported)")
    if req.depth != "basic" and not cap.depth:
        data["depth"] = "basic"
        warnings.append("stripped depth (unsupported)")
    if req.language and not cap.language:
        data["language"] = None
        warnings.append("stripped language (unsupported)")
    if req.location and not cap.location:
        data["location"] = None
        warnings.append("stripped location (unsupported)")
    if req.want_raw and not cap.raw_content:
        data["want_raw"] = False
        warnings.append("stripped want_raw (unsupported)")

    return ProjectedSearch(request=SearchRequest.model_validate(data), warnings=warnings)


def project_extract(req: ExtractRequest, cap: ExtractCapability | None) -> ProjectedExtract:
    warnings: list[str] = []
    if cap is None:
        return ProjectedExtract(request=req, warnings=["provider does not support extract"])

    data = req.model_dump()
    if req.format not in cap.formats:
        data["format"] = cap.formats[0] if cap.formats else "markdown"
        warnings.append(f"format {req.format!r} unsupported; using {data['format']!r}")
    if len(req.urls) > 1 and not cap.multi_url:
        data["urls"] = req.urls[:1]
        warnings.append("stripped extra urls (multi_url unsupported)")
    if req.only_main and not cap.only_main:
        data["only_main"] = None
        warnings.append("stripped only_main (unsupported)")

    return ProjectedExtract(request=ExtractRequest.model_validate(data), warnings=warnings)


def project_research(req: ResearchRequest, cap: ResearchCapability | None) -> ProjectedResearch:
    warnings: list[str] = []
    if cap is None:
        return ProjectedResearch(request=req, warnings=["provider does not support research"])

    data = req.model_dump()
    if req.depth not in cap.depths:
        data["depth"] = cap.depths[0] if cap.depths else "auto"
        warnings.append(f"depth {req.depth!r} unsupported; using {data['depth']!r}")

    return ProjectedResearch(request=ResearchRequest.model_validate(data), warnings=warnings)


def merge_warnings(*groups: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for g in groups:
        for w in g:
            if w and w not in seen:
                seen.add(w)
                out.append(w)
    return out
