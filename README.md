# Search Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

统一搜索网关 — 基于 provider group + instance pool 的高可用搜索入口。

**为 AI 设计的搜索网关**：多提供商自动故障转移、账号池化管理、熔断器保护，让 AI 代理始终能获得搜索结果。

## 特性

- **8 种 Provider**: Tavily, Brave, Exa, You.com, Firecrawl, Jina, SearXNG, DuckDuckGo
- **Provider Group + Instances**: 同一 provider 类型下可配置多个实例，共享通用配置
- **Circuit Breaker**: 三态断路器（CLOSED/OPEN/HALF_OPEN），自动熔断与恢复
- **两层路由**: 先选 provider，再在 provider 内选择 instance
- **三种能力**: 搜索 (search) / 内容提取 (extract) / 深度研究 (research)
- **官方 SDK 集成**: Tavily、Exa、Firecrawl 使用官方 Python SDK
- **多接口**: HTTP REST API + MCP 协议 + CLI + Python SDK
- **运行时配置**: Web UI 可视化管理 + Config API 动态增删 Provider
- **搜索历史**: 文件系统异步存储，支持查询回溯

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [MCP 集成](#mcp-集成claude-desktopcode)
- [CLI 命令](#cli-命令)
- [HTTP API](#http-api)
- [Python SDK](#python-sdk)
- [配置文件](#配置文件)
- [Provider 对比](#provider-对比)
- [开发工具](#开发工具)
- [架构设计](#架构设计)
- [贡献](#贡献)

## 快速开始

### 安装

```bash
# 全局安装（推荐）
uv tool install .

# 开发模式（代码修改自动生效）
uv tool install --editable .

# 或使用 Makefile
make install    # 全局安装
make dev        # 开发模式
```

### 配置

```bash
# 初始化配置文件（创建 ~/.sg/config.json）
sg init

# 编辑配置文件，添加 API keys
vim ~/.sg/config.json
```

配置文件示例见下方"配置文件"章节。不配置 API keys 时默认使用 DuckDuckGo（免费无限制）。

### 启动

```bash
sg start              # 默认端口 8100
sg start --port 9000  # 自定义端口
```

### MCP 集成（Claude Desktop / Claude Code）

Search Gateway 提供 MCP (Model Context Protocol) 服务器，可以集成到 Claude Desktop 和 Claude Code 中。

#### 方式一：SSE 模式（推荐）

**优势**：Gateway 持续运行，providers 只初始化一次，多个客户端可以共享同一个 gateway 实例。

**步骤：**

1. 启动 gateway 服务器：
```bash
sg start
```

2. **Claude Code 用户（推荐使用命令行配置）**：

```bash
# 方法 1：使用 claude mcp add 命令（推荐）
# 注意：必须指定 transport 为 sse，不要使用 --transport 参数
claude mcp add search-gateway sse http://127.0.0.1:8100/mcp/sse

# 方法 2：手动编辑配置文件
# 编辑 ~/.claude.json，在当前项目的 mcpServers 中添加：
```

```json
{
  "projects": {
    "/your/project/path": {
      "mcpServers": {
        "search-gateway": {
          "type": "sse",
          "url": "http://127.0.0.1:8100/mcp/sse"
        }
      }
    }
  }
}
```

3. **Claude Desktop 用户**：

找到配置文件：
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

添加配置：
```json
{
  "mcpServers": {
    "search-gateway": {
      "url": "http://127.0.0.1:8100/mcp/sse"
    }
  }
}
```

4. 重启 Claude Desktop/Code

**⚠️ 常见错误**：
- ❌ 不要使用 `claude mcp add --transport http`（会导致配置错误）
- ❌ 不要配置为 `"type": "http"`（Search Gateway 使用 SSE，不是 HTTP OAuth）
- ✅ 正确配置：`"type": "sse"` 或使用命令 `claude mcp add search-gateway sse <url>`

#### 方式二：stdio 模式

**优势**：简单，无需启动服务器，适合临时使用。每次调用会启动新的 gateway 实例。

**Claude Code 用户（推荐使用命令行配置）**：

```bash
# 使用 claude mcp add 命令
claude mcp add search-gateway stdio sg mcp

# 或手动编辑 ~/.claude.json
```

**配置文件方式**：
```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "sg",
      "args": ["mcp"]
    }
  }
}
```

#### 可用工具

MCP 服务器提供以下工具：

**search** - 搜索网络
- 参数：`query`（必需）、`provider`、`max_results`、`include_domains`、`exclude_domains`、`time_range`、`search_depth`
- 返回：文件路径 + 元数据（大小、行数、字数）

**extract** - 提取网页内容
- 参数：`urls`（必需）、`format`（markdown/text）
- 返回：提取的内容

**research** - 深度研究
- 参数：`topic`（必需）、`depth`（mini/pro/auto）
- 返回：研究报告

**list_providers** - 列出所有 provider 及状态

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

### 开发工具

项目提供了便捷的开发工具来快速更新和安装：

**使用 Makefile（推荐）：**
```bash
make install    # 安装到全局
make dev        # 开发模式安装（代码修改自动生效）
make push       # 推送并重新安装
make update     # 提交、推送、重新安装
make test       # 运行测试
make clean      # 清理缓存
make help       # 显示帮助
```

**使用脚本：**
```bash
./scripts/dev-install.sh    # 交互式提交、推送、安装
./scripts/quick-update.sh   # 快速推送并安装
```

**手动命令：**
```bash
# 快速更新流程
git add -A && git commit -m "feat: xxx" && git push && uv tool install --force .

# 开发模式（推荐）
uv tool install --editable .  # 代码修改后自动生效，无需重新安装
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

`provider` 可选，可以传 group 名或 instance 名；不指定时按当前 `executor.strategy` 自动选择。`time_range`: `day`, `week`, `month`, `year`。

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
| `/api/config/providers/{id}` | PUT | 新增/更新 provider group |
| `/api/config/providers/{id}` | DELETE | 删除 provider group |
| `/api/config/providers/{id}/instances/{instance}` | PUT | 新增/更新 provider instance |
| `/api/config/providers/{id}/instances/{instance}` | DELETE | 删除 provider instance |
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

`config.json`:

```json
{
  "server": { "host": "127.0.0.1", "port": 8100 },
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 2,
      "selection": "random",
      "defaults": { "timeout": 30000 },
      "instances": [
        {
          "id": "tavily-1",
          "enabled": true,
          "api_key": "tvly-your-api-key-here"
        }
      ]
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "selection": "random",
      "fallback_for": ["search"],
      "defaults": { "timeout": 30000 },
      "instances": [{ "id": "duckduckgo" }]
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
  "history": { "dir": "~/.sg/history" }
}
```

**说明**：
- `providers.<name>`: provider group，共享类型和通用配置
- `instances`: 该 provider 下的多个具体实例
- `selection`: provider 内实例选择策略，默认 `random`
- `priority`: provider group 的全局优先级，数值越小越优先
- `instances[].priority`: 仅用于 provider 内 `priority` 选择策略
- `is_fallback`: 兜底 provider group，所有其他 provider 都失败后使用
- `executor.strategy`: 默认 `round_robin`，在健康 provider 间轮询分摊请求
- `circuit_breaker.base_timeout`: 第一次熔断多久后允许探测
- `circuit_breaker.multiplier`: 连续熔断时的退避倍数
- `circuit_breaker.quota_timeout`: 配额耗尽时禁用多久
- `circuit_breaker.auth_timeout`: 认证失败时禁用多久
- `failover.max_attempts`: 一次请求最多尝试多少个 provider

## 当前调度策略

当前实现是两层调度：

1. 先在 provider group 之间选择
2. 再在 group 内的 instances 之间选择

### 外层：provider group 调度

- `executor.strategy = failover`
  - 按 group `priority` 固定顺序尝试
- `executor.strategy = round_robin`
  - 每次请求轮换 group 起始位置
- `executor.strategy = random`
  - 每次请求打乱 group 顺序

### 内层：group 内实例调度

- `selection = random`
  - 从当前 group 的健康实例中随机选一个
- `selection = round_robin`
  - 在当前 group 的实例间轮询
- `selection = priority`
  - 优先选择实例 `priority` 最小的那个

### 失败切换逻辑

- 某个实例失败后，会优先尝试当前 group 内的其他健康实例
- 当前 group 没有可用实例后，才切到下一个 provider group
- 正常 group 都失败后，最后再尝试 fallback group
- breaker 是实例级的，不是 provider 级的

### 指定 provider 的语义

- 如果 `provider` 传的是 group 名
  - 只在这个 group 内尝试
  - 该 group 失败后再走 fallback group
- 如果 `provider` 传的是 instance 名
  - 只尝试这个 instance
  - 失败后直接进入 fallback group
- 如果不传 `provider`
  - 按全局调度策略正常选择

### 当前默认理解

- 外层 `round_robin`
  - 在不同 provider 类型之间分散流量
- 内层 `random`
  - 在同一 provider 的多个账号之间随机分摊请求
- `failover.max_attempts = 3`
  - 一次请求最多尝试 3 个正常 group，之后再考虑 fallback

### 当前未做的事

- 不做智能 provider 推荐
- 不做结果质量打分后再换 provider
- 不把空结果自动视为失败
- 不支持旧配置格式

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

## 架构设计

Search Gateway 采用两层路由架构：

```
请求 → Executor → Provider Group 选择 → Instance 选择 → 执行
```

**核心组件**：
- **Gateway**：配置管理、API 暴露、历史记录
- **Executor**：路由策略、熔断器管理、故障转移
- **ProviderRegistry**：Provider 分组管理、实例生命周期
- **CircuitBreaker**：三态熔断器（CLOSED/OPEN/HALF_OPEN）

**路由策略**：
- 外层（Provider Group）：failover / round_robin / random
- 内层（Instance）：random / round_robin / priority

**熔断器**：
- 作用域：每个 Instance 独立
- 失败分类：瞬态（指数退避）、配额（24h）、认证（7天）

详细架构说明见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与项目。

## 许可证

[MIT License](LICENSE)

## 致谢

感谢以下搜索服务提供商：
- [Tavily](https://tavily.com/) - AI 优化的搜索 API
- [Exa](https://exa.ai/) - 语义搜索引擎
- [Brave Search](https://brave.com/search/api/) - 隐私优先的搜索
- [You.com](https://you.com/) - AI 搜索引擎
- [Firecrawl](https://firecrawl.dev/) - 网页抓取和提取
- [Jina AI](https://jina.ai/) - 神经搜索框架
- [SearXNG](https://github.com/searxng/searxng) - 元搜索引擎
- [DuckDuckGo](https://duckduckgo.com/) - 隐私搜索引擎
