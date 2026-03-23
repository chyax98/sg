# 快速开始指南

本指南帮助你在 5 分钟内开始使用 Search Gateway。

## 前置要求

- Python 3.12 或更高版本
- [uv](https://github.com/astral-sh/uv) 包管理器（推荐）

## 安装

### 使用 uv（推荐）

```bash
# 全局安装
uv tool install search-gateway

# 或从源码安装
git clone https://github.com/yourusername/search-gateway.git
cd search-gateway
uv tool install .
```

### 使用 pip

```bash
pip install search-gateway
```

## 初始化配置

```bash
# 创建配置文件
sg init

# 配置文件位置：~/.sg/config.json
```

## 基础使用

### 1. 命令行搜索

```bash
# 使用默认 provider（DuckDuckGo，免费无限制）
sg search "Python async programming"

# 指定 provider
sg search "AI news" -p brave

# 批量搜索
sg search "query1" "query2" "query3"
```

### 2. 启动 HTTP 服务器

```bash
# 启动服务器（默认端口 8100）
sg start

# 自定义端口
sg start --port 9000

# 打开 Web UI
sg web
```

### 3. MCP 集成（Claude Desktop/Code）

**SSE 模式（推荐）**：

1. 启动服务器：
```bash
sg start
```

2. 配置 Claude Desktop：
```json
{
  "mcpServers": {
    "search-gateway": {
      "url": "http://127.0.0.1:8100/mcp/sse"
    }
  }
}
```

**stdio 模式**：

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

## 添加 API Keys（可选）

编辑 `~/.sg/config.json`，添加你的 API keys：

```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 1,
      "instances": [
        {
          "id": "tavily-1",
          "api_key": "tvly-your-key-here"
        }
      ]
    }
  }
}
```

支持的 providers：
- **Tavily** - 1,000 次/月免费
- **Exa** - 1,000 次/月免费
- **Brave** - 2,000 次/月免费
- **You.com** - 有限免费
- **Firecrawl** - 500 次/月免费
- **Jina** - 免费（extract）
- **SearXNG** - 免费（需自建）
- **DuckDuckGo** - 免费无限制（默认）

## 常用命令

```bash
# 查看状态
sg status

# 查看 providers
sg providers

# 健康检查
sg health

# 查看历史
sg history

# 停止服务器
sg stop
```

## HTTP API 示例

```bash
# 搜索
curl -X POST http://localhost:8100/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Python async", "max_results": 10}'

# 内容提取
curl -X POST http://localhost:8100/extract \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'

# 深度研究
curl -X POST http://localhost:8100/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "AI trends 2026", "depth": "pro"}'
```

## Python SDK 示例

```python
from sg.sdk import SearchClient

# 同步客户端
with SearchClient() as client:
    # 搜索
    results = client.search("Python async", max_results=10)
    for r in results.results:
        print(f"{r.title}: {r.url}")

    # 内容提取
    content = client.extract(["https://example.com"])

    # 深度研究
    research = client.research("AI trends", depth="pro")

# 异步客户端
from sg.sdk import AsyncSearchClient

async with AsyncSearchClient() as client:
    results = await client.search("Python async")
```

## 下一步

- 阅读 [完整文档](../README.md)
- 查看 [架构设计](../ARCHITECTURE.md)
- 了解 [MCP 集成](mcp-integration.md)
- 查看 [测试手册](testing.md)

## 获取帮助

- 查看 [FAQ](user-guide.md#常见问题)
- 提交 [Issue](https://github.com/yourusername/search-gateway/issues)
- 阅读 [贡献指南](../CONTRIBUTING.md)
