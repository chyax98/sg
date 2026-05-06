# TinyFish Provider

TinyFish provider integrates the TinyFish Search API and Fetch API.

- Docs: <https://docs.tinyfish.ai>
- Search endpoint: `GET https://api.search.tinyfish.ai`
- Fetch endpoint: `POST https://api.fetch.tinyfish.ai`
- API key env: `TINYFISH_API_KEY`

## Capabilities

| Capability | Supported | Notes |
|---|---:|---|
| search | yes | Uses Search API |
| extract | yes | Uses Fetch API |
| research | no | Not exposed by TinyFish Search/Fetch APIs |
| include_domains / exclude_domains | yes | Implemented via `site:` / `-site:` query operators |
| time_range | no | Not documented by TinyFish Search API |
| search_depth | no | Not documented by TinyFish Search API |

## Config

```json
{
  "providers": {
    "tinyfish": {
      "type": "tinyfish",
      "enabled": true,
      "priority": 5,
      "instances": [
        {
          "id": "tinyfish-1",
          "api_key": "sk-tinyfish-*****",
          "timeout": 500000
        }
      ]
    }
  }
}
```

`api_key` may be omitted when `TINYFISH_API_KEY` is set.

Optional endpoint overrides:

```json
{
  "providers": {
    "tinyfish": {
      "type": "tinyfish",
      "instances": [
        {
          "id": "tinyfish-1",
          "env": {
            "TINYFISH_SEARCH_URL": "https://api.search.tinyfish.ai",
            "TINYFISH_FETCH_URL": "https://api.fetch.tinyfish.ai"
          }
        }
      ]
    }
  }
}
```

## Extra params

Search supports optional `extra` keys:

```json
{
  "query": "web automation tools",
  "extra": {
    "location": "US",
    "language": "en"
  }
}
```

Extract supports optional `extra` keys:

```json
{
  "urls": ["https://example.com"],
  "format": "markdown",
  "extra": {
    "links": true,
    "image_links": false
  }
}
```

Fetch requests are batched in groups of 10 URLs, matching TinyFish API limits.
