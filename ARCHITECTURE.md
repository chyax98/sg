# Architecture

## Overview

Search Gateway is a high-availability search entrypoint built around two routing layers:

1. Choose a provider group for the requested capability.
2. Choose one healthy instance inside that group.

The system optimizes for availability, not provider intelligence. It assumes users pool multiple free or low-cost accounts and want one stable search interface on top.

## Core Flow

```text
CLI / HTTP / MCP / SDK
          |
          v
       Gateway
          |
          v
       Executor
          |
          +--> choose provider groups by capability + strategy
          |
          +--> choose instance inside group
          |
          +--> circuit breaker / timeout / failover / metrics
          |
          v
    ProviderRegistry
          |
          v
  Provider groups -> instances
```

## Main Components

### Gateway

- Owns configuration, registry, executor, and history.
- Exposes `search`, `extract`, and `research`.
- Reloads config by rebuilding runtime state from disk.

### Executor

- Handles cross-group routing strategy: `failover`, `round_robin`, `random`.
- Retries within the same provider group by switching to another instance when possible.
- Applies per-instance circuit breakers and request timeouts.
- Falls back to the configured fallback group when normal groups fail.

### ProviderRegistry

- Builds provider instances from grouped config.
- Tracks group membership and fallback group.
- Selects one instance from a group based on that group's `selection` policy.
- Auto-adds `duckduckgo` only when no explicit fallback group is configured.

### CircuitBreaker

- State machine: `closed -> open -> half_open -> closed`.
- Opens per instance, not per provider type.
- Supports failure classification:
  - transient: exponential backoff
  - quota: long disable window
  - auth: longest disable window

## Configuration Shape

```json
{
  "providers": {
    "exa": {
      "type": "exa",
      "priority": 1,
      "selection": "random",
      "defaults": {
        "timeout": 30000
      },
      "instances": [
        {
          "id": "exa-1",
          "api_key": "..."
        },
        {
          "id": "exa-2",
          "api_key": "...",
          "url": "https://custom.example.com"
        }
      ]
    }
  }
}
```

Rules:

- `providers.<name>` is a provider group.
- `instances[]` contains the concrete accounts or endpoints.
- `url` is instance-level only.
- Group `priority` controls outer routing order.
- Instance `priority` is only used when group `selection` is `priority`.

## Runtime Guarantees

- A broken instance does not poison the whole provider group if other instances remain healthy.
- A failed provider group does not stop the request if other groups can serve the same capability.
- Fallback remains available even when normal providers are exhausted or temporarily disabled.
- Old config formats are not supported.
