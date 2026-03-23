# Search Capability Matrix

This project uses an adapter pattern for search providers.

The common interface is `SearchRequest`:

- `query`
- `max_results`
- `include_domains`
- `exclude_domains`
- `time_range`
- `search_depth`

Each provider adapter declares the subset it supports through `ProviderInfo.search_features`.

## Unified Params

`include_domains` / `exclude_domains`

- Native support: `tavily`, `exa`
- Query-operator based support in this gateway: `brave`, `youcom`, `firecrawl`
- Not exposed as supported: `duckduckgo`, `jina`, `searxng`

`time_range`

- Native or documented support: `tavily`, `exa`, `brave`, `youcom`, `firecrawl`, `duckduckgo`, `searxng`
- Not exposed as supported: `jina`

`search_depth`

- Native support: `tavily`
- Mapped by adapter to provider-specific mode: `exa`
- Not exposed as supported: all others

## Adapter Rules

- If a provider does not support a requested search param, the adapter raises a clear error.
- In failover mode, the executor skips that provider and tries the next one.
- For an explicit provider selection, the request fails fast instead of silently ignoring params.

## Notes

- `searxng` search syntax depends on the backing engines in the configured instance.
- `jina` public search surfaces are documented much less clearly for structured filters, so this gateway keeps its supported search surface narrow.
