# Architecture

## Overview

Search Gateway is an **AI Harness** for unified search with high availability. It's designed as a tool for AI agents (like Claude) to perform web searches through multiple providers with automatic failover.

**Core Design Principles:**
1. **AI-First**: Results are saved to files, AI reads them on demand
2. **High Availability**: Multi-provider failover with circuit breakers
3. **Account Pooling**: Manage multiple free/low-cost API accounts
4. **Simple Interface**: One stable API across all providers

## System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Client Interfaces                         │
│  CLI (sg search) │ HTTP API │ MCP Server │ Python SDK       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                        Gateway                               │
│  - Configuration management                                  │
│  - Provider registry                                         │
│  - Executor coordination                                     │
│  - History management (always-on)                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                        Executor                              │
│  Strategy: failover │ round_robin │ random                  │
│  - Group selection (by capability + strategy)                │
│  - Instance selection (within group)                         │
│  - Circuit breaker management (per instance)                 │
│  - Timeout & retry logic                                     │
│  - Capability-specific fallback                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                   ProviderRegistry                           │
│  - Provider group management                                 │
│  - Instance lifecycle (init/shutdown)                        │
│  - Capability routing                                        │
│  - Fallback group tracking                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                  Provider Instances                          │
│  Tavily │ Exa │ Brave │ You.com │ Firecrawl │ Jina │ ...   │
└─────────────────────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                    History Storage                           │
│         ~/.sg/history/YYYY-MM/timestamp-uuid.json            │
│  AI reads files on demand based on size/complexity           │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### Gateway

**Responsibilities:**
- Load and manage configuration
- Initialize provider registry and executor
- Expose unified API: `search()`, `extract()`, `research()`
- Record all search results to history files
- Support config hot-reload

**Key Methods:**
```python
async def search(query, provider=None, max_results=10, **kwargs) -> SearchResponse
async def search_batch(queries: list[str], **kwargs) -> list[SearchResponse]
async def extract(urls: list[str], **kwargs) -> ExtractResponse
async def research(topic: str, depth="auto", **kwargs) -> ResearchResponse
```

**History Management:**
- Every search is saved to `~/.sg/history/YYYY-MM/timestamp-uuid.json`
- Response includes `result_file` path
- AI decides whether to read based on file size/complexity

### Executor

**Responsibilities:**
- Implement routing strategies (failover, round_robin, random)
- Manage per-instance circuit breakers
- Handle failover across provider groups
- Apply capability-specific fallback
- Track metrics (success rate, latency, circuit breaker state)

**Routing Logic:**

1. **No provider hint:**
   - Build group list from capability + strategy
   - Try up to `max_attempts` groups
   - Fall back to fallback group if all fail

2. **Provider specified:**
   - Try specified provider group
   - Failover across instances within group
   - Fall back to fallback group if group fails

3. **Instance specified:**
   - Pin to exact instance
   - Fall back to fallback group if instance fails

**Strategies:**
- `failover`: Always start from highest priority
- `round_robin`: Rotate across groups to spread load (thread-safe)
- `random`: Random group selection

### ProviderRegistry

**Responsibilities:**
- Build provider instances from config
- Track provider groups and capabilities
- Select instances within groups
- Manage fallback group

**Group Configuration:**
```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 1,
      "selection": "random",
      "fallback_for": [],
      "instances": [
        {"id": "tavily-1", "api_key": "..."},
        {"id": "tavily-2", "api_key": "..."}
      ]
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "fallback_for": ["search"]
    }
  }
}
```

**Instance Selection:**
- `random`: Random instance (default, spreads load)
- `round_robin`: Rotate through instances (thread-safe)
- `priority`: Always pick highest priority available

### CircuitBreaker

**State Machine:**
```
CLOSED ──[failures >= threshold]──> OPEN
  ^                                   │
  │                                   │
  └──[successes >= threshold]── HALF_OPEN
                                      ^
                                      │
                              [timeout expires]
```

**Failure Classification:**
- **Transient** (500, timeout): Exponential backoff (1h → 6h → 36h, max 48h)
- **Quota** (429): Fixed 24h timeout
- **Auth** (401, 403): Fixed 7 day timeout

**Scope:**
- Per instance, not per provider type
- Isolated failures don't poison the whole group

### SearchHistory

**Responsibilities:**
- Save all search results to filesystem
- Return file path to caller
- Provide list/get/clear operations

**File Structure:**
```
~/.sg/history/
├── 2026-03/
│   ├── 20260323-103045-abc123.json
│   ├── 20260323-103102-def456.json
│   └── ...
└── 2026-04/
    └── ...
```

**File Format:**
```json
{
  "id": "20260323-103045-abc123",
  "timestamp": "2026-03-23T10:30:45Z",
  "query": "python async",
  "provider": "exa",
  "total": 10,
  "latency_ms": 843,
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "...",
      "score": 0.95
    }
  ]
}
```

## Capability-Specific Fallback

**Design:**
- Each provider can specify `fallback_for: ["search", "extract", "research"]`
- Fallback only applies to specified capabilities
- Example: DuckDuckGo as fallback for search, but not for extract

**Configuration:**
```json
{
  "duckduckgo": {
    "type": "duckduckgo",
    "fallback_for": ["search"]
  }
}
```

**Execution Flow:**
```
1. Try normal providers (by strategy)
2. If all fail, check fallback_for capability
3. If capability matches, try fallback provider
4. If fallback fails, raise error
```

## Thread Safety

**Round Robin Implementation:**
- Uses `threading.Lock` for counter access
- Safe for concurrent requests
- Prevents race conditions in multi-threaded environments

**Critical Sections:**
```python
# Executor level (group selection)
with self._rr_lock:
    idx = self._rr_index % len(groups)
    self._rr_index += 1

# Registry level (instance selection)
with self._rr_lock:
    idx = self._rr_index.get(group_name, 0) % len(available)
    self._rr_index[group_name] = idx + 1
```

## Batch Search

**Feature:**
- Execute multiple queries in parallel
- Each query gets its own history file
- Return list of file paths

**API:**
```python
# HTTP
POST /search/batch
{
  "queries": ["query1", "query2", "query3"],
  "max_results": 10
}

# CLI
sg search "query1" "query2" "query3"

# Output
query="query1" provider=exa results=10
file=/Users/xxx/.sg/history/2026-03/20260323-103045-aaa111.json (12.4KB, 287 lines, 1823 words)

query="query2" provider=tavily results=10
file=/Users/xxx/.sg/history/2026-03/20260323-103046-bbb222.json (8.2KB, 195 lines, 1205 words)
```

## Configuration Model

### Provider Group
```json
{
  "type": "tavily",           // Provider type
  "enabled": true,            // Enable/disable group
  "priority": 1,              // Group priority (lower = higher priority)
  "selection": "random",      // Instance selection: random | round_robin | priority
  "fallback_for": [],         // Capabilities this group serves as fallback
  "tags": [],                 // Optional tags
  "defaults": {               // Default settings for all instances
    "timeout": 30000
  },
  "instances": [              // Concrete instances
    {
      "id": "tavily-1",
      "enabled": true,
      "api_key": "...",
      "priority": 1,
      "timeout": 30000
    }
  ]
}
```

### Executor Config
```json
{
  "strategy": "round_robin",  // failover | round_robin | random
  "health_check": {
    "failure_threshold": 3,
    "success_threshold": 2
  },
  "circuit_breaker": {
    "base_timeout": 3600,     // 1 hour
    "multiplier": 6.0,        // Exponential backoff
    "max_timeout": 172800,    // 48 hours
    "quota_timeout": 86400,   // 24 hours for 429
    "auth_timeout": 604800    // 7 days for 401/403
  },
  "failover": {
    "max_attempts": 3
  }
}
```

### History Config
```json
{
  "dir": "~/.sg/history",
  "max_entries": 10000
}
```

## Runtime Guarantees

1. **Isolation**: Broken instance doesn't poison the whole group
2. **Failover**: Failed group doesn't stop request if others available
3. **Fallback**: Always available even when normal providers exhausted
4. **History**: Every search is recorded, no data loss
5. **Thread Safety**: Safe for concurrent requests
6. **No Legacy Support**: Old config formats not supported

## Default Configuration

**Optimized for availability with pooled accounts:**

```json
{
  "executor": {
    "strategy": "round_robin"
  },
  "providers": {
    "<group>": {
      "selection": "random"
    }
  }
}
```

**Benefits:**
- Cross-provider traffic spreading (round_robin at group level)
- Within-provider account spreading (random at instance level)
- Automatic isolation of bad instances (circuit breaker)
- Predictable fallback when capacity unavailable

## AI Integration

**Design Philosophy:**
- Gateway returns file paths, not content
- AI reads files on demand
- File metadata helps AI decide reading strategy

**Reading Strategy:**
```
File < 5KB  → Direct Read
File > 5KB  → grep/jq to filter
File > 50KB → Read specific sections
```

**Example Workflow:**
```bash
# AI calls
sg search "python async"

# Output
query="python async" provider=exa results=10
file=/Users/xxx/.sg/history/2026-03/20260323-103045-abc123.json (12.4KB, 287 lines, 1823 words)

# AI decides: file is 12KB, use jq to extract titles
jq '.results[].title' /Users/xxx/.sg/history/2026-03/20260323-103045-abc123.json
```

## Performance Characteristics

**Latency:**
- Circuit breaker check: < 1ms
- Provider selection: < 1ms
- Search request: 500-3000ms (provider dependent)
- History write: 5-20ms (async, non-blocking)

**Throughput:**
- Limited by provider rate limits
- Round robin spreads load across accounts
- Circuit breaker prevents cascading failures

**Scalability:**
- Horizontal: Add more provider instances
- Vertical: Increase `max_attempts` for more retries
- History: Filesystem-based, scales to millions of entries

## Error Handling

**Error Classification:**
```python
# Transient (retry with backoff)
- 500 Internal Server Error
- Timeout
- Connection errors

# Quota (long timeout)
- 429 Too Many Requests

# Auth (very long timeout)
- 401 Unauthorized
- 403 Forbidden

# Permanent (no retry)
- 400 Bad Request
- 404 Not Found
```

**Failure Propagation:**
```
Instance fails → Try next instance in group
Group fails → Try next group
All groups fail → Try fallback group
Fallback fails → Raise error to caller
```

## Monitoring & Metrics

**Per-Instance Metrics:**
- Total requests
- Success count
- Failure count
- Average latency
- Circuit breaker state
- Last failure type
- Disabled seconds remaining

**Access:**
```bash
sg status          # Overall status
sg providers       # Per-provider status
sg health          # Run health checks
```

**HTTP API:**
```
GET /status        # Gateway status
GET /providers     # Provider list with metrics
GET /metrics       # Detailed metrics
POST /health-check # Trigger health checks
```
