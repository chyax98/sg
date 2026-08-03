# Search Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

统一搜索网关 — 基于 provider group + instance pool 的高可用搜索入口。

**为 AI 设计的搜索网关**：多提供商自动故障转移、账号池化管理、熔断器保护，让 AI 代理始终能获得搜索结果。

## 特性

- **10 种 Provider**: Tavily, Brave, Exa, You.com, TinyFish, Firecrawl, Jina, SearXNG, Xcrawl, DuckDuckGo
- **Provider Group + Instances**: 同一 provider 类型下可配置多个实例，共享通用配置
- **Circuit Breaker**: 三态断路器（CLOSED/OPEN/HALF_OPEN），自动熔断与恢复
- **两层路由**: 先选 provider，再在 provider 内选择 instance
- **三种能力**: 搜索 (search) / 内容提取 (extract) / 深度研究 (research)
- **官方 SDK 集成**: Tavily、Exa、Firecrawl 使用官方 Python SDK
- **多接口**: HTTP REST API + MCP 协议 + CLI + Python SDK
- **运行时配置**: Web UI 可视化管理 + Config API 动态增删 Provider
- **搜索历史**: 文件系统异步存储，支持查询回溯

## 目录

- [For AI Assistants](#for-ai-assistants)
- [特性](#特性)
- [快速开始](#快速开始)
- [集成方案对比](#集成方案对比)
- [MCP 集成](#mcp-集成claude-desktopcode)
- [CLI 命令](#cli-命令)
- [HTTP API](#http-api)
- [Python SDK](#python-sdk)
- [配置文件](#配置文件)
- [Provider 对比](#provider-对比)
- [开发工具](#开发工具)
- [架构设计](#架构设计)
- [贡献](#贡献)

## For AI Assistants

如果你是 AI 编码助手在读这份 README，下面是紧凑的能力地图。

| 你想做的事 | 命令 | 文档 |
|---|---|---|
| 拿到给 AI 看的使用指南原文 | `search-gateway skill get` | [SKILL.md 打印到 stdout](#skill) |
| 让 AI 引导式帮我配置 | `search-gateway setup` | [setup prompt](prompts/setup.md) |
| 接入 OpenCode（websearch / webfetch / context7） | `search-gateway plugin install && search-gateway plugin setup` | [plugins/opencode/README.md](plugins/opencode/README.md) |
| 启动 daemon | `search-gateway start --daemon` | [docs/install/uv.md](docs/install/uv.md) |
| 搜索 / 提取 / 研究 | `search-gateway search\|extract\|research ...` | [CLI 命令](#cli-命令) |

**第一条建议**：先跑 `search-gateway skill get` 读一遍 SKILL.md，再决定要哪种集成方式。

## 集成方案对比

| 方案 | 适用场景 | 一行命令 / 配置 |
|---|---|---|
| CLI | Shell / 脚本 | `search-gateway search "q"` |
| HTTP API | 任意语言客户端 | `search-gateway start` → `http://127.0.0.1:8100` |
| MCP stdio | Claude Code/Desktop、Codex、Kimi、Gemini CLI | `claude mcp add search-gateway stdio search-gateway mcp` |
| MCP Streamable HTTP | OpenCode remote MCP | `opencode.json` 的 `mcp` 段加 `http://127.0.0.1:8100/mcp` |
| OpenCode Plugin | opencode 原生工具（覆盖内置 websearch/webfetch） | `search-gateway plugin install && search-gateway plugin setup` |
| Python SDK | Python 代码内调用 | `from sg.sdk import SearchClient` |

> 各种安装/集成方案的自闭环文档见 `docs/install/`。

## 快速开始

### 安装

```bash
# 从 GitHub 直装（推荐，无需 clone）
uv tool install git+https://github.com/chyax98/sg

# 锁版本（推荐生产用）
uv tool install "git+https://github.com/chyax98/sg@v1.0.8"

# 开发模式（clone 后代码修改自动生效）
git clone https://github.com/chyax98/sg && cd sg
uv tool install --editable .

# 或使用 Makefile（仓库内）
make install    # 全局安装
make dev        # 开发模式
```

> 不发 PyPI，安装源就是 GitHub。完整安装方案见 [docs/install/](docs/install/)。

### 配置

```bash
# 初始化配置文件（创建 ~/.sg/config.json）
search-gateway init

# 编辑配置文件，添加 API keys
vim ~/.sg/config.json
```

配置文件示例见下方"配置文件"章节。不配置 API keys 时默认使用 DuckDuckGo（免费无限制）。

### 启动

```bash
search-gateway start              # 默认端口 8100
search-gateway start --port 9000  # 自定义端口
```

### MCP 集成（Claude Desktop / Claude Code）

Search Gateway 提供 MCP (Model Context Protocol) 服务器，通过 stdio 模式集成到 Claude Desktop 和 Claude Code 中。

#### 配置方式

**Claude Code 用户（推荐使用命令行配置）**：

```bash
# 使用 claude mcp add 命令
claude mcp add search-gateway stdio search-gateway mcp

# 或手动编辑 ~/.claude.json
```

**手动配置文件方式**：

```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "search-gateway",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

**Claude Desktop 用户**：

找到配置文件：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

添加配置：
```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "/path/to/search-gateway",
      "args": ["mcp"]
    }
  }
}
```

> **注意**：`command` 需要是 `search-gateway` 的完整路径，可以通过 `which search-gateway` 获取。

#### 可用工具

面向任务的三个工具（不暴露路由/provider）：

**search** — 搜网：`query`，可选 `limit` / `domains` / `exclude_domains` / `time_range` / `depth`  
**extract** — 读页：`urls`，可选 `format`（markdown/text）  
**research** — 深研简报：`topic`，可选 `depth`（auto/mini/pro）

运维侧看 provider 状态用 CLI/`GET /providers`，不挂在 MCP 工具面上。

### CLI 命令

```bash
# 搜索
search-gateway search "MCP protocol"
search-gateway search "AI news" -p brave          # 指定 provider
search-gateway search "Python tutorial" -f json   # JSON 输出

# 内容提取
search-gateway extract https://example.com

# 深度研究
search-gateway research "AI agents trends" --depth pro

# 管理
search-gateway status       # 网关状态（含 circuit breaker 状态）
search-gateway providers    # Provider 列表
search-gateway health       # 健康检查
search-gateway history      # 搜索历史
search-gateway web          # 打开 Web UI
search-gateway stop         # 停止网关
```

## Skill

`search-gateway skill get` 是**读取方式**——打印 SKILL.md 原文到 stdout。SKILL 内容打包在包内，谁需要 sg 的使用说明，就直接调用这个命令读取：

```bash
# AI 助手运行时用 bash 工具调用，从 stdout 直接拿到内容作为上下文
search-gateway skill get

# 人想看一眼
search-gateway skill get | less
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

`provider` 可选，可以传 group 名或 instance 名；不指定时按 priority 自动选择最高优先级的 provider。`time_range`: `day`, `week`, `month`, `year`。

### 内容提取

```
POST /extract
{
  "urls": ["https://example.com"],
  "format": "markdown",
  "extract_depth": "basic"
}
```

支持 extract 的 provider：Tavily, Exa, You.com, TinyFish, Firecrawl, Jina（免费）、Xcrawl。

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
    "jina": {
      "type": "jina",
      "enabled": true,
      "priority": 70,
      "selection": "round_robin",
      "fallback_for": ["extract"],
      "instances": [{ "id": "jina-1" }]
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "selection": "round_robin",
      "fallback_for": ["search"],
      "defaults": { "timeout": 30000 },
      "instances": [{ "id": "duckduckgo" }]
    }
  },
  "executor": {
    "health_check": { "failure_threshold": 3, "success_threshold": 2 },
    "circuit_breaker": {
      "base_timeout": 300,
      "multiplier": 2,
      "max_timeout": 3600,
      "quota_timeout": 3600,
      "auth_timeout": 86400
    },
    "failover": { "max_attempts": 0 }
  },
  "history": { "dir": "~/.sg/history" }
}
```

**说明**（本地、白嫖 key 场景）：
- `providers.<name>`: provider **组**；`instances` 是组内多把 key
- `selection`: 组内选实例 — 白嫖 key 推荐 `round_robin`（轮询分摊额度）
- `priority`: 组优先级，**越小越先试**；组失败再试下一组
- `fallback_for`: 能力兜底（如 DDG→`search`，Jina→`extract`），主链路都挂了才用
- `failover.max_attempts`: 一次请求最多试几个 **组**；`0` = 试完全部候选组（推荐）
- 空结果（`results=[]` / extract 全空或全错 / research 空报告）视为失败，会换 key/换组
- `circuit_breaker.*`: 连续失败后短冷却（默认分钟级），不是多日报废

## 路由架构

本地小工具两层路由：

### 第一层：Provider Group（失败切换）

- 按 `priority` 从小到大试
- 抛错、空结果、熔断跳过 → 换下一组
- `max_attempts: 0` 时扫完全部组，再走 `fallback_for`

### 第二层：Instance（组内轮询）

同一组多把免费 key 时用 `selection`：

- **`round_robin`**：轮询（白嫖 key 推荐）
- **`random`**：随机
- **`priority`**：总用组内最高优先级实例

**示例：**
```json
{
  "providers": {
    "tavily": {
      "priority": 2,
      "selection": "round_robin",  // Group 内轮询负载均衡
      "instances": [
        { "id": "tavily-1", "priority": 1, "api_key": "key1" },
        { "id": "tavily-2", "priority": 2, "api_key": "key2" },
        { "id": "tavily-3", "priority": 3, "api_key": "key3" }
      ]
    }
  }
}
```

## Provider 对比

| Provider | 需要 Key | 免费额度 | 能力 | SDK |
|----------|---------|----------|------|-----|
| **You.com** | 是 | 有限 | search, extract | httpx |
| **TinyFish** | 是 | 按账户计划 | search, extract | httpx |
| **Tavily** | 是 | 1,000/月 | search, extract, research | tavily-python |
| **Exa** | 是 | 1,000/月 | search, extract | exa-py |
| **Firecrawl** | 是 | 500/月 | search, extract | firecrawl-py |
| **Brave** | 是 | 2,000/月 | search | httpx |
| **Jina** | 否(extract) | 免费 | extract (search 需 key) | httpx |
| **SearXNG** | 否 | 无限 | search (需自建) | httpx |
| **Xcrawl** | 是 | 有限 | search, extract | httpx |
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
