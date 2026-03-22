# Search Gateway

本地搜索聚合工具，多个搜索引擎 + DuckDuckGo 兜底。

## 架构

```
CLI (sg) ─┬─► HTTP API (FastAPI) ─┬─► Gateway ─┬─► Router (智能路由)
          │                       │            ├─► LoadBalancer (负载均衡)
          └─► MCP Server          │            └─► Registry (Provider管理)
                                  │
                                  ▼
                    ┌──────────┬──────────┬──────────┬──────────┐
                    │  Tavily  │  Brave   │   Exa    │ DuckDuckGo│
                    └──────────┴──────────┴──────────┴──────────┘
```

## 目录

```
src/sg/
├── cli.py              # sg 命令
├── core/
│   ├── router.py       # 路由
│   └── load_balancer.py
├── providers/
│   ├── base.py         # 基类
│   ├── registry.py
│   ├── tavily.py
│   ├── brave.py
│   ├── exa.py
│   └── duckduckgo.py   # 兜底
├── server/
│   ├── gateway.py
│   ├── http_server.py
│   └── mcp_server.py
└── sdk/
    └── client.py
```

## 用法

```bash
# 安装
pip install -e .

# 设置 Key（可选，不设置就用 DuckDuckGo）
export TAVILY_API_KEY="xxx"
export BRAVE_API_KEY="xxx"
export EXA_API_KEY="xxx"

# 启动
sg start

# 搜索
sg search "query"
sg search "AI news" -p brave

# 其他
sg status        # 状态
sg providers     # Provider 列表
sg health        # 健康检查
sg web           # Web UI
```

## SDK

```python
from sg.sdk import SearchClient

with SearchClient() as client:
    r = client.search("Python async")
    for item in r.results:
        print(item.title, item.url)
```

## 路由规则

| 关键词 | Provider |
|--------|----------|
| 研究/深度/research | tavily |
| 代码/github/code | exa, brave |
| 新闻/news | brave |
| 论文/paper | exa |
| 中文 | brave, tavily |
| 默认 | 轮询 |

失败自动切换，全部失败用 DuckDuckGo 兜底。

## 添加 Provider

1. 继承 `SearchProvider`
2. 实现 `initialize`, `search`, `health_check`
3. 加到 `registry.py` 的 `BUILTIN_PROVIDERS`
