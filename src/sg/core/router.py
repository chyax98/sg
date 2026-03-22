"""Router - Route queries to appropriate providers by priority."""

from ..providers.registry import ProviderRegistry


class Router:
    """Route search queries to providers by priority order."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def route(self, provider: str | None = None, capability: str = "search") -> list[str]:
        """Return ordered list of provider instance IDs to try.

        If provider is specified, return just that one.
        Otherwise, return all healthy providers sorted by priority.
        """
        if provider:
            return [provider]

        healthy = self.registry.get_healthy_providers(capability)
        if healthy:
            return [p.name for p in healthy]

        return ["duckduckgo"]
