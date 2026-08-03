"""Context7 docs side-path unit tests."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from sg.models.search import (
    DocsContextRequest,
    DocsLibraryHit,
    DocsLibrarySearchRequest,
    DocsLibrarySearchResponse,
)
from sg.providers.context7 import Context7Provider, format_library_search_text


def _mock_response(
    status: int, *, json=None, text: str = "", content_type: str = "application/json"
):
    req = httpx.Request("GET", "https://context7.com/api/v2/libs/search")
    if json is not None:
        return httpx.Response(
            status, json=json, request=req, headers={"content-type": content_type}
        )
    return httpx.Response(
        status,
        text=text,
        request=req,
        headers={"content-type": content_type},
    )


@pytest.mark.asyncio
async def test_docs_search_maps_official_fields():
    p = Context7Provider(name="c7-1", api_key="ctx7sk-test")
    await p.initialize()
    assert p._client is not None
    p._client.get = AsyncMock(
        return_value=_mock_response(
            200,
            json={
                "results": [
                    {
                        "id": "/vercel/next.js",
                        "title": "Next.js",
                        "description": "The React Framework",
                        "totalSnippets": 100,
                        "trustScore": 10,
                        "benchmarkScore": 95.5,
                        "versions": ["v15.1.8"],
                    }
                ]
            },
        )
    )

    out = await p.docs_search(
        DocsLibrarySearchRequest(library_name="Next.js", query="app router middleware")
    )
    assert out.provider == "c7-1"
    assert len(out.results) == 1
    assert out.results[0].id == "/vercel/next.js"
    assert out.results[0].benchmark_score == 95.5
    text = format_library_search_text(out)
    assert "Context7-compatible library ID: /vercel/next.js" in text
    assert "Source Reputation: High" in text
    await p.shutdown()


@pytest.mark.asyncio
async def test_docs_context_returns_plain_text():
    p = Context7Provider(name="c7-1", api_key="ctx7sk-test")
    await p.initialize()
    assert p._client is not None
    p._client.get = AsyncMock(
        return_value=_mock_response(
            200,
            text="### Middleware\n\n```ts\nexport function middleware() {}\n```",
            content_type="text/plain",
        )
    )
    out = await p.docs_context(
        DocsContextRequest(library_id="vercel/next.js", query="middleware auth")
    )
    assert out.library_id == "/vercel/next.js"
    assert "middleware" in out.content.lower()
    await p.shutdown()


@pytest.mark.asyncio
async def test_docs_search_http_error_raises_for_failover():
    p = Context7Provider(name="c7-1", api_key="ctx7sk-test")
    await p.initialize()
    assert p._client is not None
    p._client.get = AsyncMock(
        return_value=_mock_response(429, json={"message": "Rate limit exceeded"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await p.docs_search(DocsLibrarySearchRequest(library_name="react", query="hooks"))
    await p.shutdown()


def test_format_empty():
    text = format_library_search_text(
        DocsLibrarySearchResponse(library_name="x", query="y", results=[])
    )
    assert "No libraries found" in text


def test_format_hit_minimal():
    text = format_library_search_text(
        DocsLibrarySearchResponse(
            library_name="react",
            query="hooks",
            results=[DocsLibraryHit(id="/facebook/react", title="React", description="UI lib")],
        )
    )
    assert "Available Libraries" in text
    assert "/facebook/react" in text


@pytest.mark.asyncio
async def test_docs_search_failsover_to_next_key_in_group():
    """Same group multi-key: first instance 429 → second succeeds (executor + CB path)."""

    from sg.core.executor import Executor
    from sg.models.config import (
        CircuitBreakerConfig,
        ExecutorConfig,
        FailoverConfig,
        HealthCheckConfig,
    )
    from sg.providers.registry import ProviderRegistry

    ok_hit = DocsLibrarySearchResponse(
        library_name="react",
        query="hooks",
        results=[DocsLibraryHit(id="/facebook/react", title="React")],
        provider="context7-2",
    )

    bad = Context7Provider(name="context7-1", api_key="bad")
    good = Context7Provider(name="context7-2", api_key="good")
    bad.docs_search = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "429",
            request=httpx.Request("GET", "https://x"),
            response=httpx.Response(429, request=httpx.Request("GET", "https://x")),
        )
    )
    good.docs_search = AsyncMock(return_value=ok_hit)

    registry = MagicMock(spec=ProviderRegistry)
    registry.get.side_effect = lambda n: {"context7-1": bad, "context7-2": good}.get(n)
    registry.has_group.side_effect = lambda n: n == "context7"
    registry.group_for_instance.return_value = "context7"
    registry.get_fallback_group.return_value = None
    registry.get_group_order.return_value = ["context7"]

    attempted = []

    def select_instance(group_name, capability, excluded_instances=None, allow_request=None):
        for inst in (bad, good):
            if excluded_instances and inst.name in excluded_instances:
                continue
            if allow_request and not allow_request(inst.name):
                continue
            attempted.append(inst.name)
            return inst
        return None

    registry.select_instance.side_effect = select_instance

    executor = Executor(
        ExecutorConfig(
            health_check=HealthCheckConfig(),
            circuit_breaker=CircuitBreakerConfig(base_timeout=60),
            failover=FailoverConfig(max_attempts=0),
        ),
        registry,
    )

    async def op(p):
        return await p.docs_search(DocsLibrarySearchRequest(library_name="react", query="hooks"))

    result = await executor.execute("docs_search", op, provider="context7")
    assert result.provider == "context7-2"
    assert "context7-1" in attempted and "context7-2" in attempted
    assert executor._breaker("context7-1")._failure_count >= 1
