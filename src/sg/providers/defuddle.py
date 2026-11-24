"""Defuddle local extract provider — zero-cost local HTML-to-Markdown extraction.

Runs local `defuddle parse <url> --md --json` first (plus direct httpx fetch for
raw `.md` / `.txt` URLs). On HTTP 403, anti-bot walls, or empty JS/SPA shells,
raises `ProviderCapabilityError` so Executor transparently fails over to cloud
extract providers (Exa / Firecrawl / Tavily / Jina) WITHOUT tripping the
circuit breaker for normal articles.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..models.search import ExtractRequest, ExtractResponse, ExtractResult
from .base import ExtractProvider, ProviderCapabilityError, ProviderInfo, cap, extract_cap

_EXTRA_PATH_DIRS = (
    str(Path.home() / ".local" / "bin"),
    str(Path.home() / ".proto" / "shims"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
)

_RAW_TEXT_EXTENSIONS = (".md", ".mdx", ".markdown", ".txt")
_RAW_HOSTS = ("raw.githubusercontent.com", "gist.githubusercontent.com")

_BOT_OR_JS_MARKERS = (
    "just a moment...",
    "checking your browser",
    "enable javascript",
    "please turn javascript on",
    "javascript is required",
    "you need to enable javascript",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "verify you are human",
    "access denied",
    "403 forbidden",
    "bot protection",
)


def _find_defuddle_binary() -> str | None:
    found = shutil.which("defuddle")
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / "defuddle"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def _build_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    current = env.get("PATH", "")
    parts = [p for p in current.split(":") if p]
    for extra in reversed(_EXTRA_PATH_DIRS):
        if extra not in parts and Path(extra).is_dir():
            parts.insert(0, extra)
    env["PATH"] = ":".join(parts)
    return env


def _looks_like_raw_text_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if host in _RAW_HOSTS:
        return True
    return path.endswith(_RAW_TEXT_EXTENSIONS)


def _is_spa_or_blocked(content: str, title: str | None) -> str | None:
    stripped = content.strip()
    lower = f"{title or ''}\n{stripped}".lower()
    if not stripped:
        return "empty content (likely JS-rendered SPA)"
    if len(stripped) < 600:
        for marker in _BOT_OR_JS_MARKERS:
            if marker in lower:
                return f"blocked or JS-required page ({marker})"
    if len(stripped) < 40:
        return f"content too short ({len(stripped)} chars, likely SPA shell)"
    return None


class DefuddleProvider(ExtractProvider):
    """Local zero-cost Markdown extractor via `defuddle` CLI."""

    info = ProviderInfo(
        type="defuddle",
        display_name="Defuddle (Local)",
        needs_api_key=False,
        free=True,
        capability=cap(
            extract=extract_cap(formats=("markdown", "text"), multi_url=True, only_main=True)
        ),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._binary: str | None = None
        self._env: dict[str, str] = {}
        self._http: httpx.AsyncClient | None = None

    async def initialize(self) -> bool:
        self._binary = _find_defuddle_binary()
        if not self._binary:
            return False
        self._env = _build_subprocess_env()
        self._http = httpx.AsyncClient(
            timeout=min(self.timeout / 1000, 15.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SearchGateway/1.0)"},
        )
        return True

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def health_check(self) -> tuple[bool, str | None]:
        if not self._binary or not Path(self._binary).exists():
            return (False, "defuddle binary not found")
        return (True, None)

    async def _try_raw_fetch(self, url: str) -> ExtractResult | None:
        if not self._http or not _looks_like_raw_text_url(url):
            return None
        try:
            resp = await self._http.get(url)
            if resp.status_code != 200:
                return None
            ctype = (resp.headers.get("content-type") or "").lower()
            if "text/html" in ctype:
                return None
            text = resp.text.strip()
            if not text:
                return None
            title = Path(urlparse(url).path).name or None
            return ExtractResult(url=url, content=text, title=title)
        except Exception:
            return None

    async def _extract_one(self, url: str) -> ExtractResult:
        raw_hit = await self._try_raw_fetch(url)
        if raw_hit is not None:
            return raw_hit

        assert self._binary is not None
        proc = await asyncio.create_subprocess_exec(
            self._binary,
            "parse",
            url,
            "--md",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=min(self.timeout / 1000, 20.0),
            )
        except TimeoutError as e:
            proc.kill()
            await proc.wait()
            raise ProviderCapabilityError(f"defuddle timed out for {url}") from e

        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace").strip().splitlines()
            snippet = err[-1][:200] if err else f"exit {proc.returncode}"
            raise ProviderCapabilityError(f"defuddle could not fetch {url}: {snippet}")

        raw_out = stdout_b.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(raw_out)
        except json.JSONDecodeError as e:
            raise ProviderCapabilityError(f"defuddle returned non-JSON for {url}") from e

        content = str(data.get("content") or "").strip()
        title = str(data.get("title") or "").strip() or None

        reason = _is_spa_or_blocked(content, title)
        if reason:
            raise ProviderCapabilityError(f"defuddle skipped {url}: {reason}")

        return ExtractResult(url=url, content=content, title=title)

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        if not self._binary:
            raise RuntimeError("DefuddleProvider not initialized")

        start = time.perf_counter()
        results = await asyncio.gather(*[self._extract_one(url) for url in request.urls])
        latency = (time.perf_counter() - start) * 1000
        return ExtractResponse(results=list(results), provider=self.name, latency_ms=latency)
