# Search Gateway 模块设计文档

## 概述

Search Gateway 采用分层架构设计，从底层到上层依次为：

```
┌─────────────────────────────────────────────────────────┐
│  接口层 (Interface Layer)                                │
│  - CLI (cli.py)                                         │
│  - HTTP REST API (server/http_server.py)               │
│  - MCP Protocol (server/mcp_server.py)                 │
│  - Python SDK (sdk/client.py)                          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  网关层 (Gateway Layer)                                  │
│  - SearchGateway (server/gateway.py)                    │
│    统一搜索入口，协调 Executor 和 History               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  核心层 (Core Layer)                                     │
│  - Executor (core/executor.py)                          │
│    Provider 选择、故障转移、熔断器管理                   │
│  - CircuitBreaker (core/circuit_breaker.py)             │
│    三态断路器，错误分类与指数退避                        │
│  - History (core/history.py)                            │
│    搜索历史异步存储                                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Provider 层 (Provider Layer)                            │
│  - ProviderRegistry (providers/registry.py)             │
│    Provider 生命周期管理、Group/Instance 管理            │
│  - BaseProvider (providers/base.py)                     │
│    Provider 基类、能力声明                               │
│  - 具体 Provider 实现 (providers/*.py)                   │
│    Tavily, Brave, Exa, You.com, Firecrawl, etc.        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  数据模型层 (Model Layer)                                │
│  - Config Models (models/config.py)                     │
│  - Search Models (models/search.py)                     │
└─────────────────────────────────────────────────────────┘
```

---

## 1. 数据模型层 (models/)

### 1.1 models/config.py

**职责**：定义配置数据结构

**关键类**：
- `ProviderInstanceConfig`: 单个 Provider 实例配置
  - `id`: 实例唯一标识
  - `enabled`: 是否启用
  - `api_key`, `url`: 认证信息
  - `priority`: 实例优先级（用于 priority 选择策略）
  - `timeout`: 超时时间（毫秒）

- `ProviderConfig`: Provider Group 配置
  - `type`: Provider 类型（tavily, brave, exa 等）
  - `enabled`: 是否启用
  - `priority`: Group 优先级（越小越优先）
  - `selection`: 实例选择策略（random/round_robin/priority）
  - `fallback_for`: 兜底能力列表（如 ["search"]）
  - `instances`: 实例列表
  - `defaults`: 默认配置（timeout 等）

- `ExecutorConfig`: 执行器配置
  - `strategy`: 外层策略（round_robin/failover/random）
  - `failover.max_attempts`: 最大尝试次数
  - `circuit_breaker`: 熔断器参数
  - `health_check`: 健康检查参数

- `GatewayConfig`: 网关配置
  - `providers`: Provider Group 配置字典
  - `executor`: 执行器配置
  - `history.enabled`: 是否启用历史记录

### 1.2 models/search.py

**职责**：定义搜索请求/响应数据结构

**关键类**：
- `SearchRequest`: 搜索请求
  - `query`: 搜索关键词
  - `max_results`: 最大结果数
  - `include_domains`, `exclude_domains`: 域名过滤
  - `time_range`: 时间范围（day/week/month/year）
  - `search_depth`: 搜索深度（basic/advanced）

- `SearchResponse`: 搜索响应
  - `query`: 原始查询
  - `results`: 搜索结果列表
  - `total`: 结果总数
  - `provider`: 使用的 Provider 实例 ID
  - `result_file`: 结果文件路径（AI Harness 架构）

- `ExtractRequest/ExtractResponse`: 内容提取
- `ResearchRequest/ResearchResponse`: 深度研究
- `ProviderStatus`: Provider 状态信息

---

## 2. Provider 层 (providers/)

### 2.1 providers/base.py

**职责**：定义 Provider 基类和能力接口

**关键类**：
- `ProviderInfo`: Provider 元数据
  - `type`: Provider 类型标识
  - `display_name`: 显示名称
  - `needs_api_key`, `needs_url`: 配置需求
  - `free`: 是否免费
  - `capabilities`: 支持的能力（search/extract/research）
  - `search_features`: 支持的搜索特性（include_domains, time_range 等）

- `BaseProvider`: 所有 Provider 的基类
  - `initialize()`: 初始化（异步）
  - `shutdown()`: 释放资源
  - `health_check()`: 健康检查
  - `capabilities`: 能力列表

- `SearchProvider`: 搜索能力接口
  - `validate_search_request()`: 验证请求参数
  - `search()`: 执行搜索（抽象方法）

- `ExtractProvider`: 提取能力接口
  - `extract()`: 提取内容（抽象方法）

- `ResearchProvider`: 研究能力接口
  - `research()`: 深度研究（抽象方法）

**设计模式**：
- 使用 `ClassVar[ProviderInfo]` 声明 Provider 元数据
- 能力接口分离（SearchProvider, ExtractProvider, ResearchProvider）
- 参数验证前置（validate_search_request）

### 2.2 providers/registry.py

**职责**：Provider 生命周期管理、Group/Instance 管理

**关键方法**：
- `initialize()`: 初始化所有配置的 Provider Groups
  - 遍历配置，实例化 Provider
  - 构建 Group → Instances 映射
  - 自动添加 DuckDuckGo 作为默认 fallback

- `shutdown()`: 关闭所有 Provider 实例

- `get_group_order(capability)`: 获取 Group 优先级排序
  - 按 priority 排序
  - 排除 fallback Groups

- `get_fallback_group(capability)`: 获取兜底 Group

- `select_instance(group_name, capability, ...)`: 从 Group 中选择实例
  - 支持三种选择策略：priority/round_robin/random
  - 支持排除已尝试的实例
  - 支持 Circuit Breaker 过滤（allow_request）

**数据结构**：
- `_providers`: 实例 ID → Provider 对象
- `_groups`: Group 名称 → 实例 ID 列表
- `_instance_to_group`: 实例 ID → Group 名称
- `_rr_index`: Round Robin 计数器（线程安全）

### 2.3 具体 Provider 实现

每个 Provider 实现：
- 继承 `SearchProvider`/`ExtractProvider`/`ResearchProvider`
- 声明 `info: ClassVar[ProviderInfo]`
- 实现 `initialize()`, `shutdown()`, `search()`/`extract()`/`research()`

**已实现 Providers**：
- `TavilyProvider`: 使用官方 SDK，支持 search/extract/research
- `BraveProvider`: HTTP API，支持 search
- `ExaProvider`: 使用官方 SDK，支持 search/extract
- `YouComProvider`: HTTP API，支持 search
- `FirecrawlProvider`: 使用官方 SDK，支持 search/extract
- `JinaReaderProvider`: HTTP API，支持 extract
- `SearXNGProvider`: HTTP API，支持 search
- `DuckDuckGoProvider`: 使用 duckduckgo-search 库，支持 search（免费 fallback）

---

## 3. 核心层 (core/)

### 3.1 core/circuit_breaker.py

**职责**：三态断路器，自动熔断与恢复

**状态机**：
```
CLOSED (正常)
  ↓ 连续失败达到阈值
OPEN (熔断)
  ↓ 超时后
HALF_OPEN (半开探测)
  ↓ 探测成功
CLOSED (恢复)
```

**错误分类**：
- `TRANSIENT`: 临时错误（超时、5xx）→ 指数退避（1h → 6h → 36h，上限 48h）
- `QUOTA`: 配额耗尽（429）→ 禁用 24h
- `AUTH`: 认证失败（401/403）→ 禁用 7d（需人工修复）

**关键方法**：
- `allow_request()`: 是否允许请求
- `record_success()`: 记录成功（HALF_OPEN 状态下累计成功可恢复）
- `record_failure(failure_type)`: 记录失败（根据类型决定熔断策略）
- `reset()`: 手动重置（健康检查成功后调用）

**指数退避**：
- 第 1 次熔断：base_timeout (1h)
- 第 2 次熔断：base_timeout × multiplier (6h)
- 第 3 次熔断：base_timeout × multiplier² (36h)
- 上限：max_timeout (48h)

### 3.2 core/executor.py

**职责**：Provider 选择、故障转移、熔断器管理、指标收集

**执行流程**：
1. 确定候选 Provider Groups（按 capability 过滤）
2. 应用外层策略（round_robin/failover/random）排序
3. 遍历 Groups（最多 max_attempts 次）：
   - 在 Group 内按 selection 策略选择 Instance
   - 检查 Circuit Breaker 状态
   - 执行请求，成功则返回
   - 失败则尝试 Group 内其他 Instances
4. 所有正常 Groups 失败后，尝试 Fallback Group
5. 全部失败则抛出异常

**关键方法**：
- `execute(capability, operation, provider)`: 执行操作
  - `capability`: 能力类型（search/extract/research）
  - `operation`: 操作函数（接收 Provider，返回结果）
  - `provider`: 可选，指定 Provider 实例或 Group

- `_try_provider(name, provider, operation)`: 尝试单个 Provider
  - 超时控制
  - 异常分类
  - 更新 Circuit Breaker 和 Metrics

- `_candidate_groups(capability, provider)`: 构建候选 Group 列表
  - 支持指定 Provider 实例或 Group
  - 应用外层策略排序
  - 添加 Fallback Group

- `get_metrics()`: 获取所有 Provider 的指标
  - 请求数、成功数、失败数
  - 平均延迟、成功率
  - Circuit Breaker 状态

- `run_health_checks()`: 主动健康检查
  - 调用所有 Provider 的 health_check()
  - 成功则重置 Circuit Breaker

**指标收集**：
- `ProviderMetrics`: 每个 Provider 的统计信息
  - `requests`, `successes`, `failures`
  - `total_latency_ms`, `avg_latency_ms`
  - `success_rate`

### 3.3 core/history.py

**职责**：搜索历史异步存储

**存储结构**：
```
~/.sg/history/
  2026-03/
    20260323-143052-a1b2c3.json
    20260323-143105-d4e5f6.json
  2026-04/
    ...
```

**关键方法**：
- `record(request, response)`: 记录搜索历史
  - 返回文件绝对路径（AI Harness 架构）
  - 异步写入（asyncio.to_thread）
  - 按月分目录
  - 文件名：`{timestamp}-{uuid}.json`

- `list_entries()`: 列出历史记录
- `get_entry(entry_id)`: 获取单条记录
- `clear()`: 清空历史

**AI Harness 架构**：
- CLI 和 MCP 只返回文件路径 + 元数据（大小、行数、字数）
- AI 自主决定是否读取文件内容
- 避免大量结果污染上下文

---

## 4. 网关层 (server/)

### 4.1 server/gateway.py

**职责**：统一搜索入口，协调 Executor 和 History

**关键方法**：
- `search(query, ...)`: 搜索
  - 构建 SearchRequest
  - 调用 Executor.execute()
  - 记录 History
  - 设置 response.result_file

- `search_batch(queries, ...)`: 批量搜索
  - 使用 asyncio.gather() 并行执行
  - 返回 SearchResponse 列表

- `extract(url, ...)`: 内容提取
- `research(query, ...)`: 深度研究

**生命周期**：
- `initialize()`: 初始化 Registry 和 Executor
- `shutdown()`: 关闭所有组件

### 4.2 server/http_server.py

**职责**：HTTP REST API 服务器

**核心接口**：
- `POST /search`: 搜索
- `POST /search/batch`: 批量搜索
- `POST /extract`: 内容提取
- `POST /research`: 深度研究

**运维接口**：
- `GET /providers`: Provider 列表（含 breaker 状态）
- `GET /status`: 网关状态
- `POST /health-check`: 健康检查
- `GET /metrics`: 执行指标

**Config API**（运行时配置）：
- `GET /api/config`: 原始配置
- `GET /api/provider-types`: 可用 Provider 类型
- `PUT /api/config/providers/{id}`: 新增/更新 Provider
- `DELETE /api/config/providers/{id}`: 删除 Provider
- `PUT /api/config/providers/{id}/instances/{instance}`: 管理实例
- `POST /api/config/reload`: 重载配置

**History API**：
- `GET /api/history`: 搜索历史列表
- `GET /api/history/{id}`: 单条详情
- `DELETE /api/history`: 清空历史

### 4.3 server/mcp_server.py

**职责**：MCP 协议服务器（stdio 模式）

**暴露工具**：
- `search`: 搜索（返回文件路径 + 元数据）
- `extract`: 内容提取
- `research`: 深度研究
- `list_providers`: Provider 列表
- `health_check`: 健康检查

**AI Harness 架构**：
- 返回 result_file 路径而非完整结果
- 包含文件元数据（size_kb, lines, words）
- AI 自主决定读取策略

---

## 5. 接口层

### 5.1 cli.py

**职责**：命令行接口

**命令**：
- `sg start [--port 8100]`: 启动网关
- `sg stop`: 停止网关
- `sg mcp`: 启动 MCP 服务器
- `sg search <query>...`: 搜索（支持多 query 批量）
- `sg extract <url>`: 内容提取
- `sg research <topic>`: 深度研究
- `sg status`: 网关状态
- `sg providers`: Provider 列表
- `sg health`: 健康检查
- `sg history [--clear]`: 搜索历史
- `sg web`: 打开 Web UI

**AI Harness 输出**：
- 搜索命令只输出文件路径 + 元数据
- 格式：`query="..." provider=xxx results=10`
- 文件信息：`file=/path/to/file (12.3KB, 456 lines, 7890 words)`

### 5.2 sdk/client.py

**职责**：Python SDK

**用法**：
```python
from sg.sdk import SearchGatewayClient

client = SearchGatewayClient(base_url="http://localhost:8100")
response = await client.search("query")
```

---

## 6. 关键设计模式

### 6.1 两层路由

**外层（Group 级别）**：
- 策略：round_robin/failover/random
- 按 priority 排序
- Fallback Group 单独处理

**内层（Instance 级别）**：
- 策略：priority/round_robin/random
- Circuit Breaker 过滤
- 排除已尝试的实例

### 6.2 能力驱动

- 每个 Provider 声明 capabilities（search/extract/research）
- Executor 根据 capability 过滤候选 Provider
- 支持 Capability-specific fallback（fallback_for）

### 6.3 错误分类与熔断

- 错误分类：TRANSIENT/QUOTA/AUTH
- 不同错误类型采用不同熔断策略
- 指数退避恢复

### 6.4 AI Harness 架构

- 搜索结果写入文件
- 返回文件路径 + 元数据
- AI 自主决定读取策略
- 避免大量结果污染上下文

---

## 7. 数据流示例

### 搜索请求流程

```
用户 → CLI/HTTP/MCP
  ↓
SearchGateway.search()
  ↓
Executor.execute(capability="search", operation=lambda p: p.search(request))
  ↓
1. _candidate_groups("search") → [tavily, brave, exa, ..., duckduckgo(fallback)]
2. 外层策略排序（round_robin/failover/random）
3. 遍历 Groups:
   a. Registry.select_instance(group, "search") → 选择实例
   b. CircuitBreaker.allow_request() → 检查熔断状态
   c. Provider.search(request) → 执行搜索
   d. 成功 → 返回结果
   e. 失败 → 尝试 Group 内其他实例
4. 所有 Groups 失败 → 尝试 Fallback Group
5. 全部失败 → 抛出异常
  ↓
History.record(request, response) → 写入文件，返回路径
  ↓
response.result_file = 文件路径
  ↓
返回给用户（CLI 输出文件路径 + 元数据）
```

---

## 8. 配置示例

```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 2,
      "selection": "random",
      "defaults": { "timeout": 30000 },
      "instances": [
        { "id": "tavily-1", "enabled": true, "api_key": "xxx" },
        { "id": "tavily-2", "enabled": true, "api_key": "yyy" }
      ]
    },
    "duckduckgo": {
      "priority": 100,
      "fallback_for": ["search"],
      "instances": [{ "id": "duckduckgo" }]
    }
  },
  "executor": {
    "strategy": "round_robin",
    "failover": { "max_attempts": 3 },
    "circuit_breaker": {
      "base_timeout": 3600,
      "multiplier": 6.0,
      "max_timeout": 172800
    }
  }
}
```

---

## 9. 扩展指南

### 添加新 Provider

1. 在 `providers/` 下创建新文件（如 `newprovider.py`）
2. 继承 `SearchProvider`/`ExtractProvider`/`ResearchProvider`
3. 声明 `info: ClassVar[ProviderInfo]`
4. 实现 `initialize()`, `shutdown()`, `search()`/`extract()`/`research()`
5. 在 `registry.py` 的 `_register_builtins()` 中注册

### 添加新能力

1. 在 `models/search.py` 定义 Request/Response
2. 在 `providers/base.py` 定义能力接口（如 `SummarizeProvider`）
3. 在 `server/gateway.py` 添加对应方法
4. 在 HTTP/MCP/CLI 中暴露接口

---

## 10. 测试建议

### 单元测试
- Circuit Breaker 状态转换
- Executor 策略选择逻辑
- Registry 实例选择逻辑
- Provider 参数验证

### 集成测试
- 端到端搜索流程
- 故障转移场景
- 熔断器触发与恢复
- 批量搜索并发

### 性能测试
- 并发搜索吞吐量
- Circuit Breaker 开销
- History 写入性能
