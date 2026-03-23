# Search Gateway v3.0

统一搜索网关 — 聚合 8 种搜索引擎，Circuit Breaker 故障转移，DuckDuckGo 兜底。

## 特性

- **8 种 Provider**: Tavily, Brave, Exa, You.com, Firecrawl, Jina, SearXNG, DuckDuckGo
- **多实例支持**: 同一 provider 类型可配置多个实例（不同 API key）
- **Circuit Breaker**: 三态断路器（CLOSED/OPEN/HALF_OPEN），自动熔断与恢复
- **统一 Failover**: search / extract / research 全部走同一条故障转移链路
- **三种能力**: 搜索 (search) / 内容提取 (extract) / 深度研究 (research)
- **官方 SDK 集成**: Tavily、Exa、Firecrawl 使用官方 Python SDK
- **多接口**: HTTP REST API + MCP 协议 + CLI + Python SDK
- **运行时配置**: Web UI 可视化管理 + Config API 动态增删 Provider
- **搜索历史**: 文件系统异步存储，支持查询回溯

## 快速开始

### 安装

```bash
cd search-gateway
pip install -e .
```

### 配置 API Key

```bash
# 按需配置，不配置则使用 DuckDuckGo（免费无限制）
export TAVILY_API_KEY="tvly-xxx"
export BRAVE_API_KEY="BSAxxx"
export EXA_API_KEY="xxx"
export YOUCOM_API_KEY="xxx"
```


### 启动

```bash
sg start              # 默认端口 8100
sg start --port 9000  # 自定义端口
```

### MCP 集成（Claude Desktop）

```bash
sg mcp  # 启动 stdio 模式的 MCP 服务器
```

### CLI 命令

```bash
# 搜索
sg search "MCP protocol"
sg search "AI news" -p brave          # 指定 provider
sg search "Python tutorial" -f json   # JSON 输出

# 内容提取
sg extract https://example.com

# 深度研究
sg research "AI agents trends" --depth pro

# 管理
sg status       # 网关状态（含 circuit breaker 状态）
sg providers    # Provider 列表
sg health       # 健康检查
sg history      # 搜索历史
sg web          # 打开 Web UI
sg stop         # 停止网关
```

## HTTP API

### 搜索

```
POST /search
{
  "query": "MCP protocol",
  "provider": null,
  "max_results": 10,
  "include_domains": [],
  "exclude_domains": [],
  "time_range": null,
  "search_depth": "basic"
}
```

`provider` 可选，不指定则按优先级自动选择。`time_range`: `day`, `week`, `month`, `year`。

### 内容提取

```
POST /extract
{
  "urls": ["https://example.com"],
  "format": "markdown",
  "extract_depth": "basic"
}
```

支持 extract 的 provider：Tavily, Exa, Firecrawl, Jina（免费）。

### 深度研究

```
POST /research
{
  "topic": "AI agents trends 2026",
  "depth": "auto"
}
```

`depth`: `mini`, `pro`, `auto`。目前 Tavily 支持。

### 运维接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/providers` | GET | Provider 列表（含 circuit breaker 状态） |
| `/status` | GET | 网关状态 + 指标 |
| `/health-check` | POST | 主动健康检查，重置恢复的 breaker |
| `/metrics` | GET | 执行指标 |
| `/shutdown` | POST | 关闭网关 |

### Config API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/config` | GET | 原始配置 |
| `/api/provider-types` | GET | 可用 provider 类型（从类元数据派生） |
| `/api/config/providers/{id}` | PUT | 新增/更新 provider |
| `/api/config/providers/{id}` | DELETE | 删除 provider |
| `/api/config/settings` | PUT | 更新全局设置 |
| `/api/config/reload` | POST | 重载配置 |

### History API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/history` | GET | 搜索历史列表 |
| `/api/history/{id}` | GET | 单条历史详情 |
| `/api/history` | DELETE | 清空历史 |

## Python SDK

```python
from sg.sdk import SearchClient

with SearchClient() as client:
    results = client.search("MCP protocol", max_results=5)
    for r in results.results:
        print(f"- {r.title}: {r.url}")

    content = client.extract(["https://example.com"])
    research = client.research("AI agents trends", depth="pro")

# 异步
from sg.sdk import AsyncSearchClient

async with AsyncSearchClient() as client:
    results = await client.search("Python async")
```

## 配置文件

`config.json` (v3.0):

```json
{
  "version": "3.0",
  "server": { "host": "127.0.0.1", "port": 8100 },
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "api_key": "tvly-your-api-key-here",      "priority": 2,
      "timeout": 30000
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "is_fallback": true
    }
  },
  "executor": {
    "strategy": "round_robin",
    "health_check": { "failure_threshold": 3, "success_threshold": 2 },
    "circuit_breaker": {
      "base_timeout": 3600,
      "multiplier": 6,
      "max_timeout": 172800,
      "quota_timeout": 86400,
      "auth_timeout": 604800
    },
    "failover": { "max_attempts": 3 }
  },
  "history": { "enabled": true, "dir": "~/.sg/history" }
}
```

**说明**：
- `priority`: 数值越小优先级越高
- `is_fallback`: 兜底 provider，所有其他失败后使用
- `executor.strategy`: 默认 `round_robin`，在健康 provider 间轮询分摊请求
- `circuit_breaker.base_timeout`: 第一次熔断多久后允许探测
- `circuit_breaker.multiplier`: 连续熔断时的退避倍数
- `circuit_breaker.quota_timeout`: 配额耗尽时禁用多久
- `circuit_breaker.auth_timeout`: 认证失败时禁用多久
- `failover.max_attempts`: 一次请求最多尝试多少个 provider
- 旧版 v1/v2 配置会自动迁移到 v3

## Provider 对比

| Provider | 需要 Key | 免费额度 | 能力 | SDK |
|----------|---------|----------|------|-----|
| **You.com** | 是 | 有限 | search | httpx |
| **Tavily** | 是 | 1,000/月 | search, extract, research | tavily-python |
| **Exa** | 是 | 1,000/月 | search, extract | exa-py |
| **Firecrawl** | 是 | 500/月 | search, extract | firecrawl-py |
| **Brave** | 是 | 2,000/月 | search | httpx |
| **Jina** | 否(extract) | 免费 | extract (search 需 key) | httpx |
| **SearXNG** | 否 | 无限 | search (需自建) | httpx |
| **DuckDuckGo** | 否 | 无限 | search (兜底) | ddgs |

## Circuit Breaker 机制

```
正常运行 (CLOSED)
  → 短暂错误连续失败达到阈值 (failure_threshold=3)
  → 熔断 (OPEN) — 该 provider 被跳过
  → 等待退避超时 (1h → 6h → 36h → 上限 48h)
  → 半开 (HALF_OPEN) — 允许探测请求
    → 成功达到 success_threshold → 恢复 (CLOSED)
    → 任意失败 → 重新熔断并继续退避

特殊错误会立即熔断：
- `429 / quota exceeded` → 按 `quota_timeout` 禁用
- `401 / 403 / invalid api key` → 按 `auth_timeout` 禁用

`/providers` 和 `/metrics` 会返回当前 breaker 状态、剩余禁用时间和最近失败类型。
```

每个 provider 独立维护一个 Circuit Breaker。通过 `/providers` 接口可以查看各 provider 的 breaker 状态。

## 添加新 Provider

1. 在 `src/sg/providers/` 创建文件，声明 `ProviderInfo` 并继承基类
2. 实现 `initialize()`, `shutdown()`, `search()` 等方法
3. 在 `registry.py` 的 `_register_builtins()` 中注册

```python
from .base import ProviderInfo, SearchProvider

class MyProvider(SearchProvider):
    info = ProviderInfo(
        type="my_provider",
        display_name="My Provider",
        capabilities=("search",),
    )
    # ... 实现方法
```

## 许可证

MIT
