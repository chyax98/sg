# 架构设计

## 概述

Search Gateway 是一个为 AI 设计的**统一搜索网关**，具备高可用性。它专为 AI 代理（如 Claude）设计，通过多个搜索提供商执行网络搜索，并具备自动故障转移能力。

**核心设计原则：**
1. **AI 优先**：结果保存到文件，AI 按需读取
2. **高可用性**：多提供商故障转移 + 熔断器
3. **账号池化**：管理多个免费/低成本 API 账号
4. **简单接口**：跨所有提供商的统一 API

## 系统架构

```text
┌─────────────────────────────────────────────────────────────┐
│                    客户端接口                                 │
│  CLI (sg search) │ HTTP API │ MCP Server │ Python SDK       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                        Gateway                               │
│  - 配置管理                                                   │
│  - Provider 注册表                                            │
│  - Executor 协调                                              │
│  - History 管理（强制开启）                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                        Executor                              │
│  策略: failover │ round_robin │ random                       │
│  - 分组选择（按能力 + 策略）                                   │
│  - 实例选择（组内）                                            │
│  - 熔断器管理（每实例）                                        │
│  - 超时 & 重试逻辑                                             │
│  - 能力特定的 fallback                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                   ProviderRegistry                           │
│  - Provider 分组管理                                          │
│  - 实例生命周期（init/shutdown）                               │
│  - 能力路由                                                   │
│  - Fallback 分组追踪                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                  Provider 实例                                │
│  Tavily │ Exa │ Brave │ You.com │ Firecrawl │ Jina │ ...   │
└─────────────────────────────────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────────────┐
│                    历史记录存储                                │
│         ~/.sg/history/YYYY-MM/timestamp-uuid.json            │
│  AI 根据文件大小/复杂度按需读取                                 │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### Gateway

**职责：**
- 加载和管理配置
- 初始化 provider 注册表和 executor
- 暴露统一 API：`search()`、`extract()`、`research()`
- 将所有搜索结果记录到历史文件
- 支持配置热重载

**核心方法：**
```python
async def search(query, provider=None, max_results=10, **kwargs) -> SearchResponse
async def search_batch(queries: list[str], **kwargs) -> list[SearchResponse]
async def extract(urls: list[str], **kwargs) -> ExtractResponse
async def research(topic: str, depth="auto", **kwargs) -> ResearchResponse
```

**历史记录管理：**
- 每次搜索都保存到 `~/.sg/history/YYYY-MM/timestamp-uuid.json`
- 响应包含 `result_file` 路径
- AI 根据文件大小/复杂度决定是否读取

### Executor

**职责：**
- 按优先级选择 Provider Group
- 管理每实例熔断器
- 处理跨 provider 分组的故障转移
- 应用能力特定的 fallback
- 追踪指标（成功率、延迟、熔断器状态）

**路由逻辑：**

Provider Groups 始终按照 **priority 严格排序**（数字越小优先级越高）：

1. **无 provider 指定：**
   - 从最高优先级（priority 最小）的 Group 开始
   - 尝试最多 `max_attempts` 个分组
   - 失败时 failover 到下一个优先级的 Group
   - 如果全部失败则回退到 fallback 分组

2. **指定 provider group：**
   - 尝试指定的 provider 分组
   - 在组内实例间故障转移
   - 如果分组失败则回退到 fallback 分组

3. **指定具体实例：**
   - 固定到确切实例
   - 如果实例失败则回退到 fallback 分组

**两层架构：**
- **第一层（Group 选择）**：严格按 priority 排序，失败时 failover
- **第二层（Instance 选择）**：在 Group 内使用 `provider.selection` 策略负载均衡

### ProviderRegistry

**职责：**
- 从配置构建 provider 实例
- 追踪 provider 分组和能力
- 在分组内选择实例
- 管理 fallback 分组

**分组配置：**
```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 1,
      "selection": "random",
      "fallback_for": [],
      "instances": [
        {"id": "tavily-1", "api_key": "..."},
        {"id": "tavily-2", "api_key": "..."}
      ]
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "fallback_for": ["search"]
    }
  }
}
```

**实例选择：**
- `random`：随机实例（默认，分散负载）
- `round_robin`：轮询实例（线程安全）
- `priority`：总是选择最高优先级可用实例

### CircuitBreaker（熔断器）

**状态机：**
```
CLOSED ──[失败次数 >= 阈值]──> OPEN
  ^                              │
  │                              │
  └──[成功次数 >= 阈值]── HALF_OPEN
                                 ^
                                 │
                         [超时时间到期]
```

**失败分类：**
- **瞬态**（500、超时）：指数退避（1h → 6h → 36h，最大 48h）
- **配额**（429）：固定 24h 超时
- **认证**（401、403）：固定 7 天超时

**作用域：**
- 每实例，而非每 provider 类型
- 隔离的失败不会污染整个分组

### SearchHistory

**职责：**
- 分层存储：view（AI 真相源）+ trace（系统索引）
- 支持选择性读取，节省 Token
- 提供 list/get/clear 操作

**文件结构：**
```
~/.sg/history/
├── view/              # AI 真相源（JSONL 格式）
│   └── 2026-03/
│       ├── 1774293083049-abc1.txt   # 每行一个完整结果
│       └── ...
└── trace/             # 系统索引（JSON 元数据）
    └── 2026-03/
        ├── 1774293083049-abc1.json  # 只有元数据，无 results
        └── ...
```

**view 文件格式（JSONL）：**
```json
{"index": 1, "title": "...", "url": "...", "content": "...", "score": 0.95}
{"index": 2, "title": "...", "url": "...", "content": "...", "score": 0.92}
```
每行一个完整结果，支持行级选择性读取。

**trace 文件格式：**
```json
{
  "id": "1774293083049-abc1",
  "timestamp": "2026-03-24T03:12:00",
  "query": "python async",
  "provider": "exa",
  "total": 10,
  "latency_ms": 843,
  "view_file": "/Users/xxx/.sg/history/view/2026-03/1774293083049-abc1.txt"
}
```
不含 results，只存元数据和 view 文件路径。

**AI 使用流程：**
1. 调用 `search()` 获得 TOON 格式预览（含行号）
2. 根据预览判断哪些结果相关
3. 调用 `Read file line X` 只读需要的行
4. 节省 Token，避免读全量

## 能力特定的 Fallback

**设计：**
- 每个 provider 可以指定 `fallback_for: ["search", "extract", "research"]`
- Fallback 仅适用于指定的能力
- 示例：DuckDuckGo 作为 search 的 fallback，但不用于 extract

**配置：**
```json
{
  "duckduckgo": {
    "type": "duckduckgo",
    "fallback_for": ["search"]
  }
}
```

**执行流程：**
```
1. 尝试正常 providers（按策略）
2. 如果全部失败，检查 fallback_for 能力
3. 如果能力匹配，尝试 fallback provider
4. 如果 fallback 失败，抛出错误
```

## 线程安全

**Round Robin 实现：**
- 使用 `threading.Lock` 保护计数器访问
- 对并发请求安全
- 防止多线程环境中的竞态条件

**关键区域：**
```python
# Executor 层（分组选择）
with self._rr_lock:
    idx = self._rr_index % len(groups)
    self._rr_index += 1

# Registry 层（实例选择）
with self._rr_lock:
    idx = self._rr_index.get(group_name, 0) % len(available)
    self._rr_index[group_name] = idx + 1
```

## 批量搜索

**功能：**
- 并行执行多个查询
- 每个查询获得自己的历史文件
- 返回文件路径列表

**API：**
```python
# HTTP
POST /search/batch
{
  "queries": ["query1", "query2", "query3"],
  "max_results": 10
}

# CLI
sg search "query1" "query2" "query3"

# 输出（TOON 格式）
q: query1
file: /Users/xxx/.sg/history/view/2026-03/1774293083049-aaa1.txt

results[10]{line,title,url,score}:
  1,Result 1 Title,https://...,0.95
  2,Result 2 Title,https://...,0.92
  ...

To read specific results, read file lines:
  Line 1 = result [1], Line 2 = result [2], etc.

q: query2
file: /Users/xxx/.sg/history/view/2026-03/1774293083050-bbb2.txt
...
```

## 配置模型

### Provider 分组
```json
{
  "type": "tavily",           // Provider 类型
  "enabled": true,            // 启用/禁用分组
  "priority": 1,              // 分组优先级（数字越小优先级越高）
  "selection": "random",      // 实例选择：random | round_robin | priority
  "fallback_for": [],         // 此分组作为 fallback 的能力
  "tags": [],                 // 可选标签
  "defaults": {               // 所有实例的默认设置
    "timeout": 30000
  },
  "instances": [              // 具体实例
    {
      "id": "tavily-1",
      "enabled": true,
      "api_key": "...",
      "priority": 1,
      "timeout": 30000
    }
  ]
}
```

### Executor 配置
```json
{
  "health_check": {
    "failure_threshold": 3,
    "success_threshold": 2
  },
  "circuit_breaker": {
    "base_timeout": 3600,     // 1 小时
    "multiplier": 6.0,        // 指数退避
    "max_timeout": 172800,    // 48 小时
    "quota_timeout": 86400,   // 429 错误 24 小时
    "auth_timeout": 604800    // 401/403 错误 7 天
  },
  "failover": {
    "max_attempts": 3         // 最多尝试 3 个 provider group
  }
}
```

### History 配置
```json
{
  "dir": "~/.sg/history",
  "max_entries": 10000
}
```

## 运行时保证

1. **隔离**：损坏的实例不会污染整个分组
2. **故障转移**：失败的分组不会阻止请求（如果其他分组可用）
3. **Fallback**：即使正常 providers 耗尽也始终可用
4. **历史记录**：每次搜索都被记录，无数据丢失
5. **线程安全**：对并发请求安全
6. **无遗留支持**：不支持旧配置格式

## 默认配置

**针对账号池化的可用性优化：**

```json
{
  "executor": {
    "strategy": "round_robin"
  },
  "providers": {
    "<group>": {
      "selection": "random"
    }
  }
}
```

**优势：**
- 跨 provider 流量分散（分组层 round_robin）
- provider 内账号分散（实例层 random）
- 自动隔离坏实例（熔断器）
- 容量不可用时可预测的 fallback

## AI 集成

**设计理念：**
- Gateway 返回文件路径，而非内容
- AI 按需读取文件
- 文件元数据帮助 AI 决定读取策略

**读取策略：**
```
文件 < 5KB  → 直接 Read
文件 > 5KB  → grep/jq 过滤
文件 > 50KB → 读取特定部分
```

**示例工作流：**
```bash
# AI 调用
sg search "python async"

# 输出
query="python async" provider=exa results=10
file=/Users/xxx/.sg/history/2026-03/20260323-103045-abc123.json (12.4KB, 287 lines, 1823 words)

# AI 决定：文件 12KB，使用 jq 提取标题
jq '.results[].title' /Users/xxx/.sg/history/2026-03/20260323-103045-abc123.json
```

## 性能特征

**延迟：**
- 熔断器检查：< 1ms
- Provider 选择：< 1ms
- 搜索请求：500-3000ms（取决于 provider）
- 历史写入：5-20ms（异步，非阻塞）

**吞吐量：**
- 受 provider 速率限制约束
- Round robin 在账号间分散负载
- 熔断器防止级联失败

**可扩展性：**
- 水平：添加更多 provider 实例
- 垂直：增加 `max_attempts` 以获得更多重试
- 历史记录：基于文件系统，可扩展到数百万条目

## 错误处理

**错误分类：**
```python
# 瞬态（使用退避重试）
- 500 Internal Server Error
- Timeout
- Connection errors

# 配额（长超时）
- 429 Too Many Requests

# 认证（非常长的超时）
- 401 Unauthorized
- 403 Forbidden

# 永久（不重试）
- 400 Bad Request
- 404 Not Found
```

**失败传播：**
```
实例失败 → 尝试分组中的下一个实例
分组失败 → 尝试下一个分组
所有分组失败 → 尝试 fallback 分组
Fallback 失败 → 向调用者抛出错误
```

## 监控 & 指标

**每实例指标：**
- 总请求数
- 成功计数
- 失败计数
- 平均延迟
- 熔断器状态
- 最后失败类型
- 剩余禁用秒数

**访问：**
```bash
sg status          # 整体状态
sg providers       # 每 provider 状态
sg health          # 运行健康检查
```

**HTTP API：**
```
GET /status        # Gateway 状态
GET /providers     # Provider 列表及指标
GET /metrics       # 详细指标
POST /health-check # 触发健康检查
```
# AI 使用 Search Gateway 指南

## 快速开始

### 1. 基本搜索

当你需要搜索信息时，使用 `search` 工具：

```
search("Python asyncio best practices")
```

你会收到类似这样的响应：

```
q: Python asyncio best practices
file: /Users/xxx/.sg/history/view/2026-03/1774293083049-359b.txt

results[5]{line,title,url,score}:
  1,Python Asyncio Documentation,https://docs.python.org/3/library/asyncio.html,0.95
  2,Real Python: Async IO in Python,https://realpython.com/async-io-python/,0.92
  3,Asyncio Tutorial: The Complete Guide,https://superfastpython.com/asyncio-tutorial/,0.88
  4,Python Asyncio Best Practices,https://...,0.85
  5,Understanding Python Asyncio,https://...,0.82

To read specific results, read file lines:
  Line 1 = result [1], Line 2 = result [2], etc.
```

### 2. 选择性读取（关键！）

**不要**一上来就读整个文件。先看预览，选择相关的结果：

```
# 好的做法：只读相关的结果
Read file /Users/xxx/.sg/history/view/2026-03/1774293083049-359b.txt line 1
Read file /Users/xxx/.sg/history/view/2026-03/1774293083049-359b.txt line 2

# 不好的做法：读整个文件（浪费 Token）
Read file /Users/xxx/.sg/history/view/2026-03/1774293083049-359b.txt
```

## 推理流程

### 步骤 1: 分析预览

看 TOON 响应中的这几列：
- **line**: 行号，对应文件中的第几行
- **title**: 标题，判断内容相关性
- **url**: 来源域名，判断可信度
- **score**: 相关度分数（如果有）

### 步骤 2: 判断相关性

根据标题和 URL，快速判断哪些结果可能相关：

```
results[5]{line,title,url,score}:
  1,Python Asyncio Documentation,https://docs.python.org/...,0.95  ← 官方文档，必看
  2,Real Python: Async IO,https://realpython.com/...,0.92          ← 权威教程，必看
  3,某博客翻译,https://unknown-blog.com/...,0.88                     ← 可能相关
  4,Stack Overflow: asyncio error,https://stackoverflow.com/...,0.85 ← 问题排查，暂时不需要
  5,Asyncio vs Threading,https://...,0.82                           ← 对比文章，可选
```

### 步骤 3: 选择性读取

只读你判断为相关的结果：

```
# 先读最相关的 1 和 2
Read file line 1
Read file line 2

# 分析后，如果需要更多背景
Read file line 5
```

### 步骤 4: 迭代深入

如果前几个结果不够，再读更多：

```
# 发现结果 1、2 不够详细
Read file line 3
Read file line 5
```

## 节省 Token 的技巧

### 技巧 1: 分批读取

不要一次性读很多，分批来：

```
# 先读前 2 个
Read file line 1-2

# 分析后，再决定要不要读更多
Read file line 3
```

### 技巧 2: 根据分数筛选

如果结果有 score，优先读高分：

```
results[5]{line,title,url,score}:
  1,...,0.95  ← 优先
  2,...,0.92  ← 优先
  3,...,0.88  ← 其次
  4,...,0.65  ← 可能跳过
  5,...,0.62  ← 可能跳过
```

### 技巧 3: 根据域名判断

优先读权威来源：

```
  1,...,https://docs.python.org/...     ← 官方，优先
  2,...,https://realpython.com/...      ← 权威，优先
  3,...,https://medium.com/...          ← 可能有用
  4,...,https://unknown-blog.com/...    ← 谨慎
```

## 常见场景

### 场景 A: 快速事实核查

```
search("Python 3.12 release date")
→ 看预览，通常第一个结果就是答案
→ Read file line 1
→ 回答用户
```

### 场景 B: 深度研究

```
search("Python asyncio best practices", max_results=20)
→ 看预览，标记相关结果 1, 2, 5, 8, 12
→ Read file lines 1, 2, 5
→ 分析后发现还需要 8, 12
→ Read file lines 8, 12
→ 综合回答
```

### 场景 C: 对比不同观点

```
search("asyncio vs threading python")
→ 发现结果 3 支持 asyncio，结果 7 支持 threading
→ Read file line 3
→ Read file line 7
→ 对比分析两种观点
```

### 场景 D: 问题排查

```
search("asyncio "Event loop is closed" error")
→ 看预览，发现结果 2 和 4 都是关于这个错误的
→ Read file line 2
→ 如果不够，再读 line 4
→ 给出解决方案
```

## 错误示范

### ❌ 错误 1: 一上来就读整个文件

```
search("...")
→ 收到 TOON 预览
→ Read file xxx.txt  ← 错误！不要读整个文件
```

### ❌ 错误 2: 读不相关的结果

```
search("Python asyncio")
→ 看到结果 5 是关于 "JavaScript async" 的（不相关）
→ Read file line 5  ← 错误！不要读不相关的结果
```

### ❌ 错误 3: 重复读取

```
Read file line 1
Read file line 1  ← 错误！已经读过了
```

## 文件格式说明

view 文件是 JSONL 格式，每行一个完整的搜索结果：

```json
{"index": 1, "title": "...", "url": "...", "content": "...", "score": 0.95}
{"index": 2, "title": "...", "url": "...", "content": "...", "score": 0.92}
```

字段说明：
- `index`: 结果序号（从 1 开始）
- `title`: 标题
- `url`: 链接
- `content`: 完整内容
- `score`: 相关度分数（可选）
- `published_date`: 发布日期（可选）
- `author`: 作者（可选）

## 总结

记住三个原则：

1. **先看预览，再决定读什么** - 不要一上来就读文件
2. **只读相关的行** - 用 line 参数精确控制
3. **分批读取，迭代深入** - 不要一次性读太多

这样可以用最少的 Token 获取最有效的信息。
