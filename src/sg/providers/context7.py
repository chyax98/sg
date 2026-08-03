"""Context7 docs provider — side path (not web search).

Mirrors official MCP tools (@upstash/context7-mcp):
  resolve-library-id  → GET /api/v2/libs/search
  query-docs          → GET /api/v2/context

Multi-key LB is group-level (selection: random | round_robin).
"""

from __future__ import annotations

import time

import httpx

from ..models.search import (
    DocsContextRequest,
    DocsContextResponse,
    DocsLibraryHit,
    DocsLibrarySearchRequest,
    DocsLibrarySearchResponse,
    ProviderCapability,
)
from .base import BaseProvider, ProviderInfo


def _reputation_label(score: int | float | None) -> str:
    if score is None or score < 0:
        return "Unknown"
    if score >= 7:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"


def format_library_search_text(response: DocsLibrarySearchResponse) -> str:
    """Same shape as official MCP formatSearchResults."""
    if not response.results:
        return response.error or "No libraries found matching the provided name."

    blocks: list[str] = []
    for hit in response.results:
        lines = [
            f"- Title: {hit.title}",
            f"- Context7-compatible library ID: {hit.id}",
            f"- Description: {hit.description}",
        ]
        if hit.total_snippets is not None and hit.total_snippets >= 0:
            lines.append(f"- Code Snippets: {hit.total_snippets}")
        lines.append(f"- Source Reputation: {_reputation_label(hit.trust_score)}")
        if hit.benchmark_score is not None and hit.benchmark_score > 0:
            lines.append(f"- Benchmark Score: {hit.benchmark_score}")
        if hit.versions:
            lines.append(f"- Versions: {', '.join(hit.versions)}")
        blocks.append("\n".join(lines))
    return "Available Libraries:\n\n" + "\n----------\n".join(blocks)


class Context7Provider(BaseProvider):
    """Context7 Public API adapter.

    Docs: https://context7.com/docs/api-guide
    """

    info = ProviderInfo(
        type="context7",
        display_name="Context7",
        needs_api_key=True,
        free=False,
        capabilities=("docs_search", "docs_context"),
        capability=ProviderCapability(),
    )

    DEFAULT_BASE_URL = "https://context7.com/api"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        api_key = self.api_key or self.env_value("CONTEXT7_API_KEY")
        if not api_key:
            return False
        self.api_key = api_key
        base = (self.url or self.DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=base,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "*/*",
            },
            timeout=self.timeout / 1000,
            follow_redirects=True,
        )
        return True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._client:
            return (False, "Not initialized")
        return (True, None)

    def _error_message(self, resp: httpx.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("message"):
                return str(data["message"])
        except Exception:
            pass
        if resp.status_code == 429:
            return (
                "Rate limited or quota exceeded. "
                "Upgrade at https://context7.com/plans or add more API keys."
            )
        if resp.status_code == 404:
            return "The library you are trying to access does not exist."
        if resp.status_code == 401:
            return "Invalid API key. API keys should start with 'ctx7sk' prefix."
        return f"Request failed with status {resp.status_code}"

    def _raise_http(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        raise httpx.HTTPStatusError(
            self._error_message(resp),
            request=resp.request,
            response=resp,
        )

    async def docs_search(self, request: DocsLibrarySearchRequest) -> DocsLibrarySearchResponse:
        """Official: resolve-library-id → GET /v2/libs/search."""
        if not self._client:
            raise RuntimeError("Not initialized")

        library_name = request.library_name.strip()
        query = (request.query or library_name).strip()
        if not library_name:
            raise ValueError("library_name is required")
        if not query:
            raise ValueError("query is required")

        start = time.perf_counter()
        params: dict[str, str] = {
            "libraryName": library_name,
            "query": query,
        }
        if request.fast:
            params["fast"] = "true"

        resp = await self._client.get("/v2/libs/search", params=params)
        if not resp.is_success:
            # Mirror MCP: return empty + error text rather than always throwing,
            # but throw so multi-key failover can try the next instance.
            self._raise_http(resp)

        data = resp.json() if resp.content else {}
        items = data.get("results") or []
        hits: list[DocsLibraryHit] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            lib_id = str(item.get("id") or "").strip()
            if not lib_id:
                continue
            hits.append(
                DocsLibraryHit(
                    id=lib_id,
                    title=str(item.get("title") or ""),
                    description=str(item.get("description") or ""),
                    stars=item.get("stars"),
                    trust_score=item.get("trustScore"),
                    benchmark_score=item.get("benchmarkScore"),
                    total_snippets=item.get("totalSnippets"),
                    versions=[str(v) for v in (item.get("versions") or []) if v],
                    state=str(item.get("state") or ""),
                )
            )

        return DocsLibrarySearchResponse(
            library_name=library_name,
            query=query,
            results=hits,
            provider=self.name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    async def docs_context(self, request: DocsContextRequest) -> DocsContextResponse:
        """Official: query-docs → GET /v2/context (text body)."""
        if not self._client:
            raise RuntimeError("Not initialized")

        library_id = request.library_id.strip()
        query = request.query.strip()
        if not library_id:
            raise ValueError("library_id is required")
        if not query:
            raise ValueError("query is required")
        if not library_id.startswith("/"):
            library_id = f"/{library_id}"

        start = time.perf_counter()
        params: dict[str, str] = {
            "libraryId": library_id,
            "query": query,
        }
        if request.fast:
            params["fast"] = "true"

        resp = await self._client.get("/v2/context", params=params)
        self._raise_http(resp)

        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            data = resp.json() if resp.content else {}
            if isinstance(data, dict) and isinstance(data.get("data"), str):
                content = data["data"]
            else:
                content = _format_context_json(data if isinstance(data, dict) else {})
        else:
            content = (resp.text or "").strip()

        if not content:
            content = (
                "Documentation not found or not finalized for this library. "
                "Use resolve-library-id /docs/search to get a valid library ID."
            )

        return DocsContextResponse(
            library_id=library_id,
            query=query,
            content=content,
            provider=self.name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )


def _format_context_json(data: dict) -> str:
    parts: list[str] = []
    for snip in data.get("codeSnippets") or []:
        if not isinstance(snip, dict):
            continue
        title = snip.get("codeTitle") or snip.get("pageTitle") or "snippet"
        desc = snip.get("codeDescription") or ""
        src = snip.get("codeId") or ""
        parts.append(f"### {title}")
        if src:
            parts.append(f"Source: {src}")
        if desc:
            parts.append(str(desc))
        for block in snip.get("codeList") or []:
            if not isinstance(block, dict):
                continue
            lang = block.get("language") or ""
            code = block.get("code") or ""
            if code:
                parts.append(f"```{lang}\n{code}\n```")
        parts.append("")
    for snip in data.get("infoSnippets") or []:
        if not isinstance(snip, dict):
            continue
        crumb = snip.get("breadcrumb") or ""
        body = snip.get("content") or ""
        page = snip.get("pageId") or ""
        if crumb:
            parts.append(f"### {crumb}")
        if page:
            parts.append(f"Source: {page}")
        if body:
            parts.append(str(body))
        parts.append("")
    return "\n".join(parts).strip()
