# Search Gateway 日志审查报告

## 执行时间
2026-03-23

## 审查目标
检查关键路径是否有足够的日志，确保可以通过日志追踪系统行为并诊断问题。

---

## 1. 当前日志覆盖情况

### 1.1 已有日志的模块

| 模块 | Logger 状态 | 日志数量 |
|------|------------|---------|
| `core/executor.py` | ✅ 已配置 | 5 条 |
| `core/history.py` | ✅ 已配置 | 0 条 ⚠️ |
| `core/circuit_breaker.py` | ❌ 未配置 | 0 条 |
| `providers/registry.py` | ✅ 已配置 | 5 条 |
| `server/gateway.py` | ✅ 已配置 | 7 条 |
| `server/http_server.py` | ✅ 已配置 | 5 条 |
| `server/mcp_server.py` | ✅ 已配置 | 0 条 ⚠️ |
| `providers/*.py` | ❌ 未配置 | 0 条 |

---

## 2. 关键路径日志分析

### 2.1 搜索请求流程

#### ✅ 已覆盖的日志点

**Gateway 层**：
```python
# server/gateway.py
logger.info(f"Starting Search Gateway on port {self.port}")
logger.info(f"Available search providers: {available}")
logger.warning("No search providers available!")
logger.info(f"Gateway ready: http://{host}:{port}")
logger.info("Stopping Search Gateway")
logger.info("Reloading configuration...")
logger.info("Configuration reloaded")
```

**Executor 层**：
```python
# core/executor.py
logger.info(f"Provider {name} skipped: {e}")  # ProviderCapabilityError
logger.error(f"Provider {name}: auth failure, disabled for {hours:.0f}h")
logger.warning(f"Provider {name}: quota exceeded, disabled for {hours:.0f}h")
logger.warning(f"Provider {name} failed: {e}")
logger.info(f"Fallback to {provider_instance.name} succeeded")
```

**Registry 层**：
```python
# providers/registry.py
logger.warning(f"Unknown provider type: {provider_type} (group: {group_name})")
logger.info(f"Initialized: {instance_cfg.id} ({provider_type})")
logger.warning(f"Failed to initialize: {instance_cfg.id}")
logger.error(f"Error initializing {instance_cfg.id}: {e}")
logger.error(f"Error shutting down {name}: {e}")
```

#### ❌ 缺失的关键日志点

**1. Executor 执行流程缺少详细日志**

当前问题：
- 没有记录开始执行的日志（query、capability、provider）
- 没有记录 Group 选择过程
- 没有记录 Instance 选择过程
- 没有记录每次尝试的详细信息
- 没有记录最终成功的 Provider 和耗时

建议添加：
```python
# executor.py:execute() 开始
logger.info(f"Executing {capability} request, provider={provider}")
logger.debug(f"Candidate groups: {groups}")

# executor.py:execute() 循环中
logger.debug(f"Trying group: {group_name}")
logger.debug(f"Selected instance: {provider_instance.name}")

# executor.py:_try_provider() 成功时
logger.info(f"Provider {name} succeeded in {latency:.1f}ms")

# executor.py:execute() 结束
logger.info(f"Request completed: provider={provider_name}, latency={latency}ms")
```

**2. Circuit Breaker 状态变更无日志**

当前问题：
- Circuit Breaker 状态转换（CLOSED → OPEN → HALF_OPEN）没有日志
- 无法追踪熔断器何时触发、何时恢复

建议添加：
```python
# circuit_breaker.py:_open_breaker()
logger.warning(f"Circuit breaker OPENED: failure_type={failure_type}, "
               f"timeout={timeout}s, trip_count={self._trip_count}")

# circuit_breaker.py:state (HALF_OPEN)
logger.info(f"Circuit breaker entering HALF_OPEN state")

# circuit_breaker.py:record_success() (恢复)
logger.info(f"Circuit breaker CLOSED: recovered after {self._trip_count} trips")

# circuit_breaker.py:reset()
logger.info(f"Circuit breaker manually reset")
```

**3. History 记录无日志**

当前问题：
- History 写入成功/失败没有日志
- 无法追踪历史记录是否正常保存

建议添加：
```python
# history.py:record()
logger.debug(f"Recording history: query='{request.query}', provider={response.provider}")
logger.debug(f"History saved: {filepath}")

# history.py:record() 异常处理
logger.error(f"Failed to save history: {e}")
```

**4. Provider 执行无日志**

当前问题：
- 各个 Provider 的 search/extract/research 方法没有日志
- 无法追踪具体 Provider 的执行情况

建议添加：
```python
# providers/base.py 或各个 Provider
logger.debug(f"{self.name}: Starting search for '{request.query}'")
logger.debug(f"{self.name}: Got {len(results)} results in {latency}ms")
logger.error(f"{self.name}: Search failed: {e}")
```

**5. Registry 实例选择无日志**

当前问题：
- select_instance() 选择逻辑没有日志
- 无法追踪为什么选择了某个实例

建议添加：
```python
# registry.py:select_instance()
logger.debug(f"Selecting instance from group '{group_name}', "
             f"strategy={cfg.selection}, available={len(available)}")
logger.debug(f"Selected instance: {selected.name} (priority={selected.priority})")

# 当没有可用实例时
logger.warning(f"No available instances in group '{group_name}' for {capability}")
```

---

## 3. 日志级别建议

### 3.1 日志级别定义

| 级别 | 用途 | 示例 |
|------|------|------|
| **DEBUG** | 详细的诊断信息，用于开发调试 | 实例选择、参数验证、内部状态 |
| **INFO** | 关键业务流程节点 | 请求开始/完成、Provider 成功、配置重载 |
| **WARNING** | 可恢复的异常情况 | Provider 失败（会重试）、配额耗尽、初始化失败 |
| **ERROR** | 严重错误，需要关注 | 认证失败、所有 Provider 失败、配置错误 |

### 3.2 推荐的日志级别分配

**Executor**：
- `DEBUG`: 候选 Group 列表、实例选择、每次尝试
- `INFO`: 请求开始、请求完成（含 Provider 和耗时）、Fallback 成功
- `WARNING`: Provider 失败（临时错误、配额）
- `ERROR`: 认证失败、所有 Provider 失败

**Circuit Breaker**：
- `INFO`: 状态转换（HALF_OPEN、CLOSED）、手动重置
- `WARNING`: 熔断触发（OPEN）

**Registry**：
- `DEBUG`: 实例选择过程
- `INFO`: Provider 初始化成功
- `WARNING`: Provider 初始化失败、未知 Provider 类型、无可用实例
- `ERROR`: 初始化异常、关闭异常

**Gateway**：
- `INFO`: 启动、停止、配置重载、可用 Provider 列表
- `WARNING`: 无可用 Provider

**History**：
- `DEBUG`: 记录保存、文件路径
- `ERROR`: 保存失败

**Providers**：
- `DEBUG`: 请求开始、结果统计
- `ERROR`: 执行失败

---

## 4. 日志格式建议

### 4.1 统一日志格式

建议在应用启动时配置统一的日志格式：

```python
# 推荐格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 输出示例
2026-03-23 14:30:52 [INFO] sg.core.executor: Executing search request, provider=None
2026-03-23 14:30:52 [DEBUG] sg.core.executor: Candidate groups: ['tavily', 'brave', 'duckduckgo']
2026-03-23 14:30:52 [DEBUG] sg.core.executor: Trying group: tavily
2026-03-23 14:30:52 [DEBUG] sg.providers.registry: Selected instance: tavily-1 (priority=10)
2026-03-23 14:30:53 [INFO] sg.core.executor: Provider tavily-1 succeeded in 856.3ms
2026-03-23 14:30:53 [INFO] sg.core.executor: Request completed: provider=tavily-1, latency=856ms
```

### 4.2 结构化日志（可选）

对于生产环境，建议使用结构化日志（JSON 格式）：

```python
import structlog

logger = structlog.get_logger()

# 使用示例
logger.info("request_completed",
    capability="search",
    provider="tavily-1",
    latency_ms=856.3,
    results=10,
    query="python async"
)

# 输出 JSON
{"event": "request_completed", "capability": "search", "provider": "tavily-1",
 "latency_ms": 856.3, "results": 10, "query": "python async",
 "timestamp": "2026-03-23T14:30:53.123Z"}
```

---

## 5. 测试场景与预期日志

### 5.1 正常搜索流程

**场景**：使用默认 Provider 搜索

**预期日志**：
```
[INFO] sg.server.gateway: Executing search request, query='python async'
[DEBUG] sg.core.executor: Candidate groups: ['tavily', 'brave', 'duckduckgo']
[DEBUG] sg.core.executor: Trying group: tavily
[DEBUG] sg.providers.registry: Selected instance: tavily-1 (priority=10)
[DEBUG] sg.providers.tavily: tavily-1: Starting search for 'python async'
[INFO] sg.core.executor: Provider tavily-1 succeeded in 856.3ms
[DEBUG] sg.core.history: Recording history: query='python async', provider=tavily-1
[DEBUG] sg.core.history: History saved: /Users/xxx/.sg/history/2026-03/20260323-143052-a1b2c3.json
[INFO] sg.server.gateway: Request completed: provider=tavily-1, latency=856ms, results=10
```

### 5.2 Provider 故障转移

**场景**：第一个 Provider 失败，自动切换到第二个

**预期日志**：
```
[INFO] sg.server.gateway: Executing search request, query='python async'
[DEBUG] sg.core.executor: Candidate groups: ['tavily', 'brave', 'duckduckgo']
[DEBUG] sg.core.executor: Trying group: tavily
[DEBUG] sg.providers.registry: Selected instance: tavily-1 (priority=10)
[WARNING] sg.core.executor: Provider tavily-1 failed: HTTPStatusError(500)
[DEBUG] sg.core.executor: Trying group: brave
[DEBUG] sg.providers.registry: Selected instance: brave-1 (priority=10)
[INFO] sg.core.executor: Provider brave-1 succeeded in 1234.5ms
[INFO] sg.server.gateway: Request completed: provider=brave-1, latency=1234ms, results=8
```

### 5.3 Circuit Breaker 触发

**场景**：Provider 连续失败 3 次，触发熔断

**预期日志**：
```
[WARNING] sg.core.executor: Provider tavily-1 failed: Timeout
[WARNING] sg.core.executor: Provider tavily-1 failed: Timeout
[WARNING] sg.core.executor: Provider tavily-1 failed: Timeout
[WARNING] sg.core.circuit_breaker: Circuit breaker OPENED: provider=tavily-1, failure_type=transient, timeout=3600s, trip_count=1
[DEBUG] sg.providers.registry: Instance tavily-1 excluded by circuit breaker
[DEBUG] sg.providers.registry: Selected instance: tavily-2 (priority=10)
```

### 5.4 认证失败

**场景**：API Key 无效

**预期日志**：
```
[ERROR] sg.core.executor: Provider tavily-1: auth failure, disabled for 168h
[WARNING] sg.core.circuit_breaker: Circuit breaker OPENED: provider=tavily-1, failure_type=auth, timeout=604800s, trip_count=1
[DEBUG] sg.core.executor: Trying group: brave
[INFO] sg.core.executor: Provider brave-1 succeeded in 987.6ms
```

### 5.5 Fallback 触发

**场景**：所有正常 Provider 失败，使用 Fallback

**预期日志**：
```
[WARNING] sg.core.executor: Provider tavily-1 failed: Timeout
[WARNING] sg.core.executor: Provider brave-1 failed: Timeout
[DEBUG] sg.core.executor: All normal providers failed, trying fallback
[DEBUG] sg.core.executor: Trying fallback group: duckduckgo
[DEBUG] sg.providers.registry: Selected instance: duckduckgo (priority=100)
[INFO] sg.core.executor: Fallback to duckduckgo succeeded
[INFO] sg.server.gateway: Request completed: provider=duckduckgo, latency=543ms, results=10
```

### 5.6 批量搜索

**场景**：同时搜索 3 个 query

**预期日志**：
```
[INFO] sg.server.gateway: Executing batch search: 3 queries
[INFO] sg.server.gateway: Executing search request, query='python async'
[INFO] sg.server.gateway: Executing search request, query='rust tokio'
[INFO] sg.server.gateway: Executing search request, query='go goroutine'
[INFO] sg.core.executor: Provider tavily-1 succeeded in 856ms
[INFO] sg.core.executor: Provider brave-1 succeeded in 923ms
[INFO] sg.core.executor: Provider tavily-2 succeeded in 1045ms
[INFO] sg.server.gateway: Batch search completed: 3/3 succeeded
```

---

## 6. 日志配置建议

### 6.1 开发环境

```python
# 开发环境：详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
```

### 6.2 生产环境

```python
# 生产环境：关键日志 + 文件输出
import logging
from logging.handlers import RotatingFileHandler

# Console handler (INFO+)
console = logging.StreamHandler()
console.setLevel(logging.INFO)

# File handler (DEBUG+, 轮转)
file_handler = RotatingFileHandler(
    'logs/search-gateway.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)

# 配置 root logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[console, file_handler]
)
```

### 6.3 环境变量控制

```python
# 支持通过环境变量控制日志级别
import os

log_level = os.getenv('SG_LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
```

---

## 7. 优先级改进建议

### P0（必须添加）

1. **Executor 执行流程日志**
   - 请求开始/完成（INFO）
   - Provider 成功/失败（INFO/WARNING）
   - 最终结果统计（INFO）

2. **Circuit Breaker 状态变更日志**
   - 熔断触发（WARNING）
   - 状态恢复（INFO）

### P1（强烈建议）

3. **Registry 实例选择日志**
   - 选择过程（DEBUG）
   - 无可用实例（WARNING）

4. **History 记录日志**
   - 保存成功（DEBUG）
   - 保存失败（ERROR）

5. **Provider 执行日志**
   - 请求开始（DEBUG）
   - 结果统计（DEBUG）

### P2（可选）

6. **HTTP Server 请求日志**
   - 请求接收（INFO）
   - 响应返回（INFO）

7. **MCP Server 工具调用日志**
   - 工具调用（INFO）
   - 调用结果（INFO）

---

## 8. 实施计划

### 阶段 1：核心日志（1-2 小时）
- [ ] Executor 执行流程日志
- [ ] Circuit Breaker 状态变更日志
- [ ] 配置统一日志格式

### 阶段 2：详细日志（2-3 小时）
- [ ] Registry 实例选择日志
- [ ] History 记录日志
- [ ] Provider 执行日志

### 阶段 3：生产优化（1-2 小时）
- [ ] 添加日志轮转
- [ ] 添加环境变量控制
- [ ] 添加结构化日志（可选）

---

## 9. 测试验证

### 9.1 日志完整性测试

运行以下测试场景，验证日志是否完整：

```bash
# 1. 正常搜索
sg search "python async"

# 2. 指定 Provider
sg search "python async" -p tavily

# 3. Provider 不存在
sg search "python async" -p nonexistent

# 4. 批量搜索
sg search "python async" "rust tokio" "go goroutine"

# 5. 触发熔断（需要模拟 Provider 失败）
# 连续请求一个配置错误的 Provider

# 6. 配置重载
curl -X POST http://localhost:8100/api/config/reload
```

### 9.2 日志分析

检查日志是否包含：
- ✅ 每个请求的完整生命周期
- ✅ Provider 选择过程
- ✅ 失败原因和重试逻辑
- ✅ 熔断器状态变更
- ✅ 最终执行结果

---

## 10. 总结

### 当前状态
- ✅ 基础日志框架已建立
- ⚠️ 关键路径日志不完整
- ❌ 缺少详细的诊断日志

### 改进后效果
- ✅ 可以追踪每个请求的完整生命周期
- ✅ 可以诊断 Provider 故障和熔断问题
- ✅ 可以分析性能瓶颈
- ✅ 可以监控系统健康状态

### 建议
**立即添加 P0 日志**，确保生产环境可以追踪关键问题。P1 和 P2 日志可以根据实际需求逐步添加。
