# Search Gateway 用户故事

## 故事 1：指定 Provider 但允许 Failover

### 场景
作为用户，我希望优先使用 Tavily 搜索，但如果它暂时不可用，自动尝试其他 provider，而不是直接失败。

### 使用示例

```bash
# CLI: 指定 Tavily，但它失败了会自动切换
sg search "MCP protocol" --provider tavily

# 输出:
# Search: MCP protocol
#   Provider: brave (tavily failed, quota exceeded) | 10 results | 850ms
```

```python
# SDK: 指定 provider 作为偏好
from sg.sdk import SearchClient

with SearchClient() as client:
    result = client.search("MCP protocol", provider="tavily")
    print(f"Used: {result.provider}")  # 可能是 "brave"，如果 tavily 失败
    print(f"Attempted: {result.meta.attempted}")
    # [
    #   {"provider": "tavily", "status": "failed", "error": "quota_exceeded"},
    #   {"provider": "brave", "status": "success"}
    # ]
```

```json
// HTTP API
{
  "query": "MCP protocol",
  "provider": "tavily"
}

// Response:
{
  "query": "MCP protocol",
  "provider": "brave",
  "results": [...],
  "meta": {
    "attempted": [
      {"provider": "tavily", "status": "failed", "error": "quota_exceeded", "latency_ms": 120},
      {"provider": "brave", "status": "success", "latency_ms": 730}
    ]
  }
}
```

### 价值
- 表达偏好但不牺牲可用性
- 了解系统实际使用了哪个 provider
- 透明的故障转移过程

---

## 故事 2：空结果继续搜索

### 场景
作为用户，我希望当某个 provider 返回 0 条结果时，系统自动尝试其他 provider，而不是直接给我空结果。

### 使用示例

```bash
# Tavily 返回 0 条结果，自动尝试 Brave
sg search "非常冷门的查询"

# 输出:
# Search: 非常冷门的查询
#   Provider: brave (tavily returned 0 results) | 3 results | 1200ms
```

### 配置

```json
{
  "executor": {
    "failover": {
      "empty_result_failover": true
    }
  }
}
```

### 价值
- 最大化获得结果的机会
- 不依赖单个 provider 的覆盖度
- 特别适合长尾查询

---

## 故事 3：了解搜索过程

### 场景
作为用户，我想知道一次搜索到底经历了什么，为什么最终使用了某个 provider。

### 使用示例

```bash
# 查看详细搜索过程
sg search "AI news" -v

# 输出:
# Search: AI news
#   Attempted:
#     1. tavily-main: OPEN (circuit breaker) - skipped
#     2. tavily-backup: failed (quota exceeded) - 150ms
#     3. brave-1: success - 680ms
#   Provider: brave-1 | 10 results | 830ms total
```

```python
# 程序化访问尝试历史
result = client.search("AI news")
for attempt in result.meta.attempted:
    print(f"{attempt.provider}: {attempt.status} ({attempt.latency_ms}ms)")
```

### 价值
- 透明了解系统行为
- 排查问题时知道发生了什么
- 验证配置是否生效

---

## 故事 4：管理 Provider 状态

### 场景
作为用户，我想知道当前哪些 provider 可用，哪些被熔断了，以及什么时候恢复。

### 使用示例

```bash
# 查看 provider 状态
sg status

# 输出:
# Search Gateway Status
#   Running: true
#   Port: 8100
#   Providers:
#     ✓ brave-1: healthy (5/5 success, 120ms avg)
#     ✗ tavily-main: OPEN (quota exceeded, retry in 23h)
#     ✓ tavily-backup: healthy (3/3 success, 150ms avg)
#     ✓ exa-1: healthy (4/5 success, 200ms avg)
#     ✓ duckduckgo: fallback, healthy
```

```bash
# 查看 metrics
sg providers

# 输出:
# Available Providers
#   + brave-1 [brave]
#       Capabilities: search
#       Priority: 2
#       Circuit: closed
#       Metrics: 45/50 success, 120ms avg
#   - tavily-main [tavily]
#       Capabilities: search, extract, research
#       Priority: 1
#       Circuit: OPEN
#       Retry in: 23h 15m
#       Last failure: quota
```

### 价值
- 了解系统健康状况
- 知道何时需要干预
- 验证故障转移是否正常工作

---

## 故事 5：配置多实例负载均衡

### 场景
作为用户，我有多个 Tavily API key，希望它们能自动轮询使用，分散额度消耗。

### 配置

```json
{
  "providers": {
    "tavily-main": {
      "type": "tavily",
      "api_key": "tvly-key-1",
      "priority": 1
    },
    "tavily-backup": {
      "type": "tavily",
      "api_key": "tvly-key-2",
      "priority": 1
    },
    "tavily-trial": {
      "type": "tavily",
      "api_key": "tvly-key-3",
      "priority": 2
    }
  },
  "executor": {
    "strategy": "round_robin"
  }
}
```

### 行为
- 请求按 round_robin 分布在 tavily-main 和 tavily-backup 之间
- 如果两者都失败，尝试 tavily-trial
- 如果都熔断，fallback 到 DuckDuckGo

### 价值
- 最大化免费额度利用率
- 延长整体可用时间
- 自动处理单个 key 失效

---

## 故事 6：快速切换 Provider

### 场景
作为用户，我发现某个 provider 最近不稳定，想暂时停用它。

### 使用示例

```bash
# 通过 Web UI 或 API 临时禁用
sg config disable tavily-main

# 或修改 config.json
{
  "providers": {
    "tavily-main": {
      "enabled": false
    }
  }
}

# 重新加载配置
sg reload
```

### 价值
- 快速响应 provider 问题
- 无需重启服务
- 灵活控制流量

---

## 故事 7：MCP 集成

### 场景
作为 Claude Desktop 用户，我想通过 MCP 使用搜索，但希望它能自动处理 provider 故障。

### 配置

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "search": {
      "command": "sg",
      "args": ["mcp"],
      "env": {
        "SG_CONFIG": "/path/to/config.json"
      }
    }
  }
}
```

### 使用

```
User: 搜索最新的 MCP 协议更新

Claude: 我来帮您搜索...
[调用 search tool]

Claude: 找到了 10 条结果（通过 brave，因为 tavily 暂时不可用）...
```

### 价值
- LLM 无需了解 provider 细节
- 自动获得高可用搜索能力
- 透明的故障转移

---

## 汇总：核心价值主张

| 用户痛点 | Search Gateway 解决方案 |
|---------|------------------------|
| 单个 API key 额度用完 | 多 key 自动轮询 + failover |
| 某个 provider 不稳定 | Circuit breaker 自动熔断 + 切换 |
| 不想维护多个搜索接口 | 统一接口，自动选择 provider |
| 空结果频繁出现 | 空结果自动触发 failover |
| 不知道发生了什么 | 透明的尝试历史 + 状态查看 |
| 配置复杂 | 最小化配置，合理默认值 |

> **无论指定哪个 provider，内容总会到来。**
