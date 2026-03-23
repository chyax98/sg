# Search Gateway v3.0 架构

## 概述

搜索聚合网关。多个搜索引擎 API 统一在单一接口后面，通过 Circuit Breaker + 优先级 Failover 保证可用性。

## 架构图

```
用户接口
┌──────────────────────────────────────────────────────────┐
│  CLI (sg)    HTTP API (FastAPI)    MCP Server    SDK     │
└───────────────────────┬──────────────────────────────────┘
                        │
核心                     ▼
┌──────────────────────────────────────────────────────────┐
│                      Gateway                             │
│  ┌──────────────────────────┐  ┌────────────────────┐   │
│  │       Executor            │  │   SearchHistory    │   │
│  │  (failover + breaker +   │  │  (async file I/O)  │   │
│  │   metrics + timeout)     │  └────────────────────┘   │
│  └────────────┬─────────────┘                            │
│               │ per-provider                             │
│  ┌────────────▼─────────────┐                            │
│  │    CircuitBreaker × N     │                            │
│  │  CLOSED → OPEN → HALF_OPEN                            │
│  └──────────────────────────┘                            │
└───────────────────────┬──────────────────────────────────┘
                        │
Provider 层              ▼
┌──────────────────────────────────────────────────────────┐
│                  ProviderRegistry                        │
│  ┌────────┐ ┌───────┐ ┌─────┐ ┌──────────┐              │
│  │You.com │ │Tavily │ │ Exa │ │ Firecrawl │              │
│  │ httpx  │ │  SDK  │ │ SDK │ │    SDK    │              │
│  └────────┘ └───────┘ └─────┘ └──────────┘              │
│  ┌───────┐ ┌──────┐ ┌────────┐ ┌──────────────────┐    │
│  │ Brave │ │ Jina │ │SearXNG │ │ DuckDuckGo (兜底) │    │
│  │ httpx │ │httpx │ │ httpx  │ │  ddgs + to_thread │    │
│  └───────┘ └──────┘ └────────┘ └──────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

## 目录结构

```
src/sg/
├── __init__.py                # v3.0.0
├── __main__.py
├── _entry.py
├── cli.py                     # Click CLI (start/stop/mcp/search/extract/research/...)
│
├── models/
│   ├── config.py              # GatewayConfig, ProviderConfig, ExecutorConfig, ...
│   └── search.py              # SearchRequest/Response, ExtractRequest/Response, ...
│
├── core/
│   ├── circuit_breaker.py     # 三态断路器 (CLOSED/OPEN/HALF_OPEN)
│   ├── executor.py            # 统一执行器：failover + breaker + timeout + metrics
│   └── history.py             # 异步文件系统搜索历史
│
├── providers/
│   ├── base.py                # ProviderInfo + BaseProvider/SearchProvider/ExtractProvider/ResearchProvider
│   ├── registry.py            # 生命周期管理，类型元数据自动派生
│   ├── tavily.py              # tavily-python SDK
│   ├── exa.py                 # exa-py SDK
│   ├── firecrawl.py           # firecrawl-py SDK
│   ├── brave.py               # httpx
│   ├── youcom.py              # httpx
│   ├── jina.py                # httpx (extract 免费, search 需 key)
│   ├── searxng.py             # httpx (自建实例)
│   └── duckduckgo.py          # ddgs + asyncio.to_thread
│
├── server/
│   ├── gateway.py             # 主编排器
│   ├── http_server.py         # FastAPI HTTP 服务
│   └── mcp_server.py          # FastMCP stdio/HTTP 服务
│
└── sdk/
    └── client.py              # SearchClient (sync) + AsyncSearchClient
```

## 核心组件

### Gateway (`server/gateway.py`)

编排器。组装 Executor + Registry + History，暴露 `search()`, `extract()`, `research()` 三个核心方法。每个方法都通过 `executor.execute(capability, operation, provider)` 走统一的 failover 链路。

### Executor (`core/executor.py`)

v3.0 的核心改进。合并了旧版的 Router + LoadBalancer 为单一组件：

- **Provider 选择**: 按 capability 过滤 + circuit breaker 过滤 + priority 排序
- **负载分散**: 默认 `round_robin`，在健康 provider 间轮询起始点
- **Failover 执行**: 依次尝试 candidates，失败自动切换下一个
- **Circuit Breaker**: 每个 provider 一个独立 breaker，自动熔断和恢复
- **Timeout**: 使用 `asyncio.timeout` 强制执行超时
- **Metrics**: 请求数/成功/失败/延迟/成功率 + breaker 状态

### CircuitBreaker (`core/circuit_breaker.py`)

三态断路器，per-provider 独立：

```
CLOSED (正常)
  └─ transient failure_count >= failure_threshold ──→ OPEN (熔断，跳过该 provider)
                                                        └─ time > current_timeout ──→ HALF_OPEN (探测)
                                                                                       ├─ 成功 × success_threshold ──→ CLOSED
                                                                                       └─ 任一失败 ──→ OPEN
```

`current_timeout` 不是固定值，而是指数退避：
- 第 1 次熔断: `base_timeout`
- 第 2 次熔断: `base_timeout * multiplier`
- 第 N 次熔断: 直到 `max_timeout`

特殊错误会直接打开 breaker：
- `AUTH`: 401/403/invalid api key，按 `auth_timeout` 禁用
- `QUOTA`: 429/quota exceeded，按 `quota_timeout` 禁用

### ProviderRegistry (`providers/registry.py`)

Provider 生命周期管理：
- 根据 config 实例化 provider（支持多实例）
- 自动添加 DuckDuckGo 兜底
- 按 capability 查询 + priority 排序
- Provider 类型信息从 `ProviderInfo` 类变量自动派生（不再硬编码）

### SearchHistory (`core/history.py`)

文件系统存储，所有 I/O 通过 `asyncio.to_thread` 异步执行，不阻塞事件循环。

## Provider 体系

### 自描述元数据

每个 Provider 类声明 `ProviderInfo`：

```python
class TavilyProvider(SearchProvider, ExtractProvider, ResearchProvider):
    info = ProviderInfo(
        type="tavily",
        display_name="Tavily",
        capabilities=("search", "extract", "research"),
    )
```

Registry 通过读取 `info` 派生类型列表，消除了硬编码。

### 基类继承

```
BaseProvider (ABC)
├── SearchProvider      → search(SearchRequest) → SearchResponse
├── ExtractProvider     → extract(ExtractRequest) → ExtractResponse
└── ResearchProvider    → research(ResearchRequest) → ResearchResponse
```

多能力 provider 通过多继承组合。

### SDK 选择策略

| Provider | 方式 | 原因 |
|----------|------|------|
| Tavily | tavily-python SDK | 官方维护，async，处理 auth/polling |
| Exa | exa-py SDK | 官方维护，typed responses，多搜索模式 |
| Firecrawl | firecrawl-py SDK | 官方维护，async，search+scrape 一体 |
| 其余 | raw httpx | API 简单（1-2 endpoint），无官方 SDK 或 SDK 不成熟 |
| DuckDuckGo | ddgs + to_thread | 同步库，通过 to_thread 避免阻塞 |

## 请求处理流程

所有操作走同一条链路：

```
Gateway.search/extract/research(params)
  │
  ├─ 构建 Request + operation lambda
  │
  └─ Executor.execute(capability, operation, provider?)
       │
       ├─ _candidates(capability): 按 capability 过滤 → breaker 过滤 → priority 排序/轮询
       │
       └─ for name in candidates[:max_attempts]:
            ├─ breaker.allow_request()? → 跳过 OPEN 的 provider
            ├─ asyncio.timeout(provider.timeout) 包装
            ├─ await operation(provider)
            │   ├─ 成功 → breaker.record_success() → metrics++ → return
            │   └─ 失败 → classify_error() → breaker.record_failure(type) → metrics++ → continue
            │
            └─ 全部失败 → 尝试 fallback (DuckDuckGo) → 仍失败 → RuntimeError
```

## 配置系统

### 版本迁移

v1/v2 配置自动迁移到 v3：
- `load_balancer` → `executor`
- 删除 `routing`, `cache`, `weight`, `transport` 等废弃字段
- `weighted` / `least_connections` 迁移为 `round_robin`

### 环境变量


## 接口层

### HTTP Server

FastAPI，使用 config 中的 host 绑定（不再硬编码 0.0.0.0）。

### MCP Server

`sg mcp` 启动 stdio 模式 MCP 服务器，暴露 search/extract/research/list_providers 四个 tool，供 Claude Desktop 等 LLM 客户端调用。

### CLI

所有命令（除 `sg start` 和 `sg mcp`）通过 HTTP API 与运行中的 Gateway 通信。

### SDK

`SearchClient`（sync）和 `AsyncSearchClient`（async），封装 HTTP 调用，返回类型化响应（`SearchResponse`, `ExtractResponse`, `ResearchResponse`）。
