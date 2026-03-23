# MCP 集成指南

Search Gateway 提供 MCP (Model Context Protocol) 服务器，可以集成到 Claude Desktop 和 Claude Code 中。

## 两种集成模式

### SSE 模式（推荐）

**优势**：
- Gateway 持续运行，providers 只初始化一次
- 多个客户端可以共享同一个 gateway 实例
- 更高效，适合生产环境

**配置步骤**：

1. 启动 gateway 服务器：
```bash
sg start
```

2. 配置 Claude Desktop/Code 的 `claude_desktop_config.json`：
```json
{
  "mcpServers": {
    "search-gateway": {
      "url": "http://127.0.0.1:8100/mcp/sse"
    }
  }
}
```

3. 重启 Claude Desktop/Code

### stdio 模式

**优势**：
- 简单，无需启动服务器
- 适合临时使用

**配置步骤**：

1. 配置 Claude Desktop/Code 的 `claude_desktop_config.json`：
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

2. 重启 Claude Desktop/Code

---

## Claude Desktop 集成

### 配置文件位置

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### 完整配置示例

如果你有多个 MCP 服务器：

```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "sg",
      "args": ["mcp"],
      "env": {
        "SG_LOG_LEVEL": "INFO"
      }
    },
    "other-server": {
      "command": "other-mcp-server",
      "args": []
    }
  }
}
```

---

## Claude Code 集成

### 配置步骤

1. 找到 Claude Code MCP 配置文件：
   - 位置: `~/.config/claude-code/mcp_settings.json`

2. 添加 Search Gateway 服务器：

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

3. 重启 Claude Code 或重新加载配置

4. 验证：在 Claude Code 中使用搜索功能

### 使用自定义配置文件

如果你的配置文件不在默认位置：

```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "sg",
      "args": ["mcp", "--config", "/path/to/config.json"]
    }
  }
}
```

---

## 可用工具

MCP 服务器暴露以下工具：

### 1. search

搜索网络，支持多个搜索引擎和自动故障转移。

**参数**：
- `query` (必需): 搜索查询
- `provider` (可选): 指定 provider (tavily, brave, exa, youcom, searxng, duckduckgo)
- `max_results` (可选): 最大结果数，默认 10
- `include_domains` (可选): 限制搜索域名列表
- `exclude_domains` (可选): 排除域名列表
- `time_range` (可选): 时间范围 (day, week, month, year)
- `search_depth` (可选): 搜索深度 (basic, advanced)

**返回**：文件路径 + 元数据（大小、行数、字数）

**示例**：
```
search(query="Python async programming 2026", max_results=10)
```

### 2. extract

从网页提取干净的内容。

**参数**：
- `urls` (必需): URL 列表
- `format` (可选): 输出格式 (markdown, text)，默认 markdown

**返回**：提取的内容（直接返回，不保存文件）

**示例**：
```
extract(urls=["https://docs.python.org/3/tutorial/"], format="markdown")
```

### 3. research

对主题进行深度研究，综合多个来源。

**参数**：
- `topic` (必需): 研究主题或问题
- `depth` (可选): 研究深度 (mini, pro, auto)，默认 auto

**返回**：研究报告（直接返回）

**示例**：
```
research(topic="Impact of AI on software development", depth="pro")
```

### 4. list_providers

列出所有可用的搜索 provider 及其状态。

**参数**：无

**返回**：Provider 列表及状态信息

---

## 使用最佳实践

### 1. 搜索结果处理

search 工具返回文件路径，Claude 需要读取文件获取完整结果：

- **小文件 (<5KB)**: 直接读取整个文件
- **中文件 (5-50KB)**: 使用 jq 提取关键字段
- **大文件 (>50KB)**: 使用 jq 切片读取前几个结果

### 2. Provider 选择

- 不指定 provider：自动选择，带故障转移
- 指定 provider：优先使用该 provider，失败后仍会故障转移
- 使用 `list_providers` 查看可用 provider

### 3. 错误处理

如果搜索失败：
1. 使用 `list_providers` 检查 provider 状态
2. 检查是否有 provider 处于 DOWN 状态
3. 尝试指定不同的 provider

---

## 故障排查

### MCP 服务器无法启动

**症状**：Claude 无法连接到 Search Gateway

**解决方案**：
1. 检查 `sg` 命令是否在 PATH 中：
   ```bash
   which sg
   ```

2. 手动测试 MCP 服务器：
   ```bash
   sg mcp
   ```
   应该看到服务器启动日志

3. 检查配置文件是否存在：
   ```bash
   ls ~/.sg/config.json
   ```
   如果不存在，运行 `sg init`

### 搜索返回空结果

**症状**：搜索成功但没有结果

**解决方案**：
1. 检查 provider 状态：
   ```bash
   sg providers
   ```

2. 检查 API Key 配置（如果使用需要 Key 的 provider）

3. 尝试使用 DuckDuckGo（免费，无需 Key）：
   ```
   search(query="test", provider="duckduckgo")
   ```

### Circuit Breaker 打开

**症状**：Provider 显示 DOWN 状态

**解决方案**：
1. 查看状态：
   ```bash
   sg status
   ```

2. 如果是认证错误，检查 API Key

3. 运行健康检查重置：
   ```bash
   sg health
   ```

---

## 高级配置

### 自定义日志级别

```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "sg",
      "args": ["mcp"],
      "env": {
        "SG_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### 使用自定义配置

```json
{
  "mcpServers": {
    "search-gateway": {
      "command": "sg",
      "args": ["mcp", "--config", "~/.sg/custom-config.json"]
    }
  }
}
```

---

## 示例对话

### 搜索最新信息

**用户**: "Search for the latest Python 3.13 features"

**Claude**: 使用 `search` 工具，读取结果文件，总结关键特性

### 提取文章内容

**用户**: "Extract the content from https://example.com/article"

**Claude**: 使用 `extract` 工具，返回干净的 markdown 内容

### 深度研究

**用户**: "Research the impact of AI on software development in 2026"

**Claude**: 使用 `research` 工具，返回综合研究报告

---

## 参考资源

- [MCP 协议规范](https://modelcontextprotocol.io/)
- [Search Gateway 架构文档](../ARCHITECTURE.md)
- [用户指南](user-guide.md)
