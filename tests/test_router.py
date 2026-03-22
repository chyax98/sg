"""Tests for Router."""

import pytest
from unittest.mock import MagicMock

from sg.core.router import Router
from sg.providers.base import SearchProvider


class MockProvider(SearchProvider):
    def __init__(self, name, priority=10):
        super().__init__(priority=priority)
        self._name = name
        self.capabilities = ["search"]

    @property
    def name(self):
        return self._name

    async def initialize(self):
        return True

    async def shutdown(self):
        pass

    async def health_check(self):
        return True, None

    async def search(self, request):
        pass


class TestRouter:

    def test_route_with_explicit_provider(self):
        """Explicit provider returns just that provider."""
        registry = MagicMock()
        router = Router(registry=registry)
        assert router.route(provider="tavily-main") == ["tavily-main"]

    def test_route_returns_healthy_by_priority(self):
        """No explicit provider returns healthy providers sorted by priority."""
        registry = MagicMock()
        p1 = MockProvider("brave-1", priority=5)
        p2 = MockProvider("tavily-main", priority=1)
        p3 = MockProvider("exa-1", priority=10)
        registry.get_healthy_providers.return_value = [p2, p1, p3]  # already sorted

        router = Router(registry=registry)
        result = router.route()
        assert result == ["tavily-main", "brave-1", "exa-1"]

    def test_route_fallback_to_duckduckgo(self):
        """No healthy providers falls back to duckduckgo."""
        registry = MagicMock()
        registry.get_healthy_providers.return_value = []

        router = Router(registry=registry)
        assert router.route() == ["duckduckgo"]

    def test_route_with_capability(self):
        """Route passes capability to registry."""
        registry = MagicMock()
        registry.get_healthy_providers.return_value = []

        router = Router(registry=registry)
        router.route(capability="extract")
        registry.get_healthy_providers.assert_called_with("extract")
