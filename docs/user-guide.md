# Search Gateway 用户指南

完整的安装、配置和使用指南。

---

## 目录

- [安装](#安装)
- [初始化](#初始化)
- [配置 API Key](#配置-api-key)
- [基本使用](#基本使用)
- [MCP 集成](#mcp-集成)
- [常见问题](#常见问题)
- [最佳实践](#最佳实践)

---

## 安装

### 方式 1: 全局安装（推荐）

使用 uv 全局安装：

```bash
uv tool install git+https://github.com/your-org/search-gateway.git
```

或从本地安装：

```bash
cd search-gateway
uv tool install .
```

验证安装：

```bash
sg --help
```

### 方式 2: 开发模式

```bash
cd search-gateway
pip install -e .
```

---

## 初始化

首次使用前，运行初始化命令创建配置文件：

```bash
sg init
```

这会：
- 创建 `~/.sg/config.json` 配置文件
- 配置默认 provider (DuckDuckGo，免费无需 API Key)
- 显示可用 provider 列表

配置文件位置：`~/.sg/config.json`

---

## 配置 API Key

### 查看可用 Provider

```bash
sg providers
```

### 编辑配置文件

```bash
# macOS/Linux
nano ~/.sg/config.json

# 或使用 Web UI
sg start && sg web
```

### Provider 配置示例

```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 1,
      "selection": "random",
      "instances": [
        {
          "id": "tavily-1",
          "enabled": true,
          "api_key": "tvly-your-api-key-here"
        }
      ]
    },
    "exa": {
      "type": "exa",
      "enabled": true,
      "priority": 2,
      "selection": "random",
      "instances": [
        {
          "id": "exa-1",
          "enabled": true,
          "api_key": "your-exa-api-key",
          "url": "https://api.exa.ai"
        }
      ]
    }
  }
}
```

### 免费 Provider

无需 API Key 的 provider：
- **DuckDuckGo**: 免费搜索，无限制（默认 fallback）
- **Jina**: 免费内容提取
- **SearXNG**: 需要自建实例

---

## 基本使用

### 启动网关

```bash
sg start
```

默认端口 8100，访问：
- HTTP API: http://127.0.0.1:8100
- Web UI: http://127.0.0.1:8100

自定义端口：

```bash
sg start --port 9000
```

### 搜索

**单个查询**：

```bash
sg search "Python async programming"
```

**批量查询**（并行执行）：

```bash
sg search "Python" "Rust" "Go"
```

**指定 provider**：

```bash
sg search "AI news" -p tavily
```

**高级选项**：

```bash
sg search "Python tutorial" \
  --max 20 \
  --include-domain python.org \
  --time-range week \
  --search-depth advanced
```

### 内容提取

```bash
sg extract https://docs.python.org/3/tutorial/
```

多个 URL：

```bash
sg extract https://example.com/page1 https://example.com/page2
```

### 深度研究

```bash
sg research "AI trends 2026" --depth pro
```

深度选项：
- `mini`: 快速研究，较少来源
- `pro`: 深度研究，更多来源
- `auto`: 自动选择（默认）

### 查看结果

搜索返回文件路径，根据文件大小选择查看方式：

**小文件 (<5KB)**：

```bash
cat /path/to/result.json
```

**中文件 (5-50KB)**：

```bash
jq '.results[] | {title, url}' /path/to/result.json
```

**大文件 (>50KB)**：

```bash
jq '.results[0:5]' /path/to/result.json
```

### 管理命令

**查看状态**：

```bash
sg status
```

**查看 provider 列表**：

```bash
sg providers
```

**健康检查**：

```bash
sg health
```

**查看历史**：

```bash
sg history
```

**停止网关**：

```bash
sg stop
```

---

## MCP 集成

详细的 MCP 集成指南请参考 [MCP 集成文档](mcp-integration.md)。

### 快速配置

**Claude Desktop**：

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

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

**Claude Code**：

编辑 `~/.config/claude-code/mcp_settings.json`：

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

---

## 常见问题

### Q: 配置文件在哪里？

A: `~/.sg/config.json`

如果不存在，运行 `sg init` 创建。

### Q: 如何添加新的 API Key？

A: 编辑 `~/.sg/config.json`，在对应 provider 的 `instances` 中添加：

```json
{
  "id": "tavily-2",
  "enabled": true,
  "api_key": "your-new-key"
}
```

或使用 Web UI：`sg start && sg web`

### Q: Provider 显示 DOWN 状态怎么办？

A: 检查 circuit breaker 状态：

```bash
sg status
```

如果是认证错误，检查 API Key。运行健康检查重置：

```bash
sg health
```

### Q: 搜索返回空结果？

A: 可能原因：
1. Provider 熔断器打开 - 运行 `sg health`
2. API Key 无效 - 检查配置
3. 网络问题 - 检查连接

尝试使用 DuckDuckGo（免费，无需 Key）：

```bash
sg search "test" -p duckduckgo
```

### Q: 如何查看日志？

A: 启动时指定日志文件：

```bash
sg start --log-level DEBUG --log-file ~/.sg/logs/gateway.log
```

查看日志：

```bash
tail -f ~/.sg/logs/gateway.log
```

### Q: 网关自动启动失败？

A: 检查：
1. `sg` 命令是否在 PATH 中：`which sg`
2. 配置文件是否存在：`ls ~/.sg/config.json`
3. 端口是否被占用：`lsof -i :8100`

### Q: 如何使用自定义配置文件？

A: 使用 `--config` 参数：

```bash
sg start --config /path/to/custom-config.json
sg search "query" --config /path/to/custom-config.json
```

### Q: 如何卸载？

A: 如果使用 uv tool 安装：

```bash
uv tool uninstall search-gateway
```

删除配置和历史：

```bash
rm -rf ~/.sg
```

---

## 最佳实践

### 1. Provider 配置

**优先级设置**：
- 高质量 provider（Tavily, Exa）设置低优先级数字（1-5）
- 免费 provider（DuckDuckGo）设置高优先级数字（100）作为 fallback

**多实例配置**：
- 同一 provider 配置多个 API Key 实例
- 使用 `selection: "random"` 分散负载
- 避免单点故障

### 2. 搜索策略

**使用场景**：
- 快速查询：不指定 provider，自动选择
- 特定需求：指定 provider（如 Tavily 的 research 功能）
- 批量查询：使用批量搜索并行执行

**参数优化**：
- `max_results`: 根据需求调整，避免过大
- `time_range`: 查找最新信息时使用
- `include_domains`: 限制权威来源

### 3. 结果处理

**文件读取**：
- 小文件：直接读取
- 大文件：使用 jq 过滤
- 批量处理：编写脚本处理多个结果文件

**历史管理**：
- 定期清理历史：`sg history --clear`
- 历史位置：`~/.sg/history/`

### 4. 性能优化

**并行查询**：

```bash
sg search "query1" "query2" "query3"
```

**后台运行**：

```bash
sg start &
```

**资源限制**：
- 控制 `max_results` 避免过大响应
- 使用 circuit breaker 自动隔离故障 provider

### 5. 安全建议

**API Key 管理**：
- 不要在代码中硬编码 API Key
- 使用配置文件管理
- 定期轮换 API Key

**访问控制**：
- 默认绑定 127.0.0.1，仅本地访问
- 如需远程访问，使用反向代理 + 认证

---

## 进阶主题

### 自定义 Provider

参考 [架构文档](../ARCHITECTURE.md) 了解如何添加新 provider。

### Web UI 使用

启动后访问 http://127.0.0.1:8100：
- 可视化配置 provider
- 实时查看 provider 状态
- 测试搜索功能

### HTTP API

完整 API 文档参考 [README](../README.md#http-api)。

示例：

```bash
curl -X POST http://127.0.0.1:8100/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Python async", "max_results": 10}'
```

---

## 获取帮助

- GitHub Issues: https://github.com/your-org/search-gateway/issues
- 文档：查看 `docs/` 目录
- 命令帮助：`sg --help`

---

## 相关文档

- [架构说明](../ARCHITECTURE.md)
- [MCP 集成指南](mcp-integration.md)
- [测试手册](testing.md)
- [产品蓝图](product-blueprint.md)
