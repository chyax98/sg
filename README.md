# Search Gateway

统一搜索网关 - 聚合多个搜索引擎，支持负载均衡和智能路由。

## 特性

- **多 Provider 支持**: Tavily, Brave, Exa, DuckDuckGo (兜底)
- **负载均衡**: 加权轮询、故障自动转移
- **智能路由**: 根据查询内容自动选择最佳搜索引擎
- **统一接口**: HTTP REST API + MCP 协议
- **SDK 支持**: Python 同步/异步客户端
- **Web UI**: 可视化配置和测试

## 快速开始

### 安装

```bash
cd search-gateway
pip install -e .
```

### 配置环境变量

```bash
export TAVILY_API_KEY="tvly-xxx"
export BRAVE_API_KEY="BSAxxx"
export EXA_API_KEY="xxx"
```

### 启动服务

```bash
# 启动网关
sg start

# 指定端口
sg start --port 8100
```

### CLI 搜索

```bash
# 基本搜索
sg search "MCP protocol 2025"

# 指定 provider
sg search "AI news" --provider brave

# JSON 输出
sg search "Python tutorial" --format json
```

### CLI 其他命令

```bash
# 查看状态
sg status

# 列出 providers
sg providers

# 健康检查
sg health

# 提取网页
sg extract https://example.com https://example.org

# 深度研究
sg research "AI agents 2025 trends" --depth pro

# 启动 Web UI
sg web
```

## API 接口

### 搜索

```bash
POST /search
{
  "query": "MCP protocol",
  "provider": null,  // 可选，不指定则自动路由
  "max_results": 10,
  "include_domains": [],
  "exclude_domains": [],
  "time_range": null  // day, week, month, year
}
```

### 提取

```bash
POST /extract
{
  "urls": ["https://example.com"],
  "provider": "tavily",  // 或 exa
  "format": "markdown",
  "extract_depth": "basic"
}
```

### 深度研究

```bash
POST /research
{
  "topic": "AI agents trends 2025",
  "depth": "auto"  // mini, pro, auto
}
```

### 其他接口

- `GET /providers` - 列出所有 providers
- `GET /status` - 网关状态
- `POST /health-check` - 健康检查
- `GET /metrics` - 负载均衡指标

## Python SDK

```python
from sg.sdk import SearchClient

# 同步客户端
with SearchClient() as client:
    # 搜索
    results = client.search("MCP protocol 2025", max_results=5)
    for r in results.results:
        print(f"- {r.title}: {r.url}")

    # 指定 provider
    results = client.search("AI news", provider="brave")

    # 提取网页
    content = client.extract(["https://example.com"])

    # 深度研究
    research = client.research("AI agents trends", depth="pro")

# 异步客户端
from sg.sdk import AsyncSearchClient

async with AsyncSearchClient() as client:
    results = await client.search("Python async")
```

## 配置文件

编辑 `config.json`:

```json
{
  "providers": {
    "tavily": {
      "enabled": true,
      "api_key": "${TAVILY_API_KEY}",
      "priority": 10,
      "weight": 5
    }
  },
  "routing": {
    "research": {
      "patterns": ["(研究|深度|research)"],
      "providers": ["tavily"]
    }
  },
  "load_balancer": {
    "strategy": "weighted",
    "failover": {
      "enabled": true,
      "retry_count": 2
    }
  }
}
```

## Provider 对比

| Provider | 免费额度 | 特色功能 |
|----------|----------|----------|
| **Tavily** | 1,000/月 | search + extract + crawl + research |
| **Brave** | 2,000/月 | 搜索操作符 + 新闻 + 图片 |
| **Exa** | 1,000/月 | 语义搜索 + 学术/代码分类 |
| **DuckDuckGo** | 无限制 | 兜底方案，无需 API key |

## 路由规则

默认路由规则：

- **研究/分析** → Tavily (深度研究)
- **代码/编程** → Exa + Brave
- **新闻** → Brave
- **学术** → Exa (学术分类)
- **中文** → Brave + Tavily
- **其他** → 轮询 Tavily, Brave, Exa

兜底：所有失败自动切换到 DuckDuckGo

## 许可证

MIT
