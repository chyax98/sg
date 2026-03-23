# 测试手册

黑盒测试用例，基于 `sg` CLI 进行验证。

## 环境准备

```bash
# 启动网关（DEBUG 级别，输出到文件）
sg start --log-level DEBUG --log-file ~/.sg/logs/test.log

# 查看实时日志
tail -f ~/.sg/logs/test.log
```

---

## TC-001 单个搜索请求

**验证**：基本搜索功能

```bash
sg search "python async"
```

预期：
- 返回文件路径 + 元数据（大小/行数/字数）
- `provider=exa-1`（最高优先级）

日志关键词：`Provider exa-1 succeeded`

---

## TC-002 批量搜索

**验证**：并行执行多个查询

```bash
sg search "python" "rust" "go"
```

预期：
- 返回 3 个文件路径
- 日志中 3 个请求时间戳几乎相同（并行）

---

## TC-003 指定 Provider

**验证**：`-p` 参数锁定 provider group

```bash
sg search "test" -p tavily
```

预期：
- `provider=tavily-*`
- 日志：`Candidate groups: ['tavily']`

---

## TC-004 Provider 绝对优先级

**验证**：多次请求总是从最高优先级 provider 开始

```bash
sg search "test1" && sg search "test2" && sg search "test3"
```

预期（日志）：
```
Candidate groups: ['exa', 'tavily', 'youcom', ...]
Trying group: exa
```
三次请求均如此，不轮转。

---

## TC-005 Instance 选择策略

**验证**：group 内 round_robin

前置：将 tavily 的 `selection` 改为 `round_robin`，禁用 exa。

```bash
sg search "test1" && sg search "test2" && sg search "test3"
```

预期：tavily-2 和 tavily-3 交替出现。

测试后恢复配置。

---

## TC-006 Provider 故障转移

**验证**：provider 失败后自动切换到下一个

前置：将 exa 的 `api_key` 改为无效值。

```bash
sg search "test failover"
```

预期：
- `provider=tavily-*`
- 日志：`Trying group: exa` → `Trying group: tavily`

测试后恢复配置。

---

## TC-007 所有 Provider 失败后使用 Fallback

**验证**：全部常规 provider 失败时使用 duckduckgo

前置：禁用除 duckduckgo 外的所有 provider。

```bash
sg search "test fallback"
```

预期：
- `provider=duckduckgo`
- 日志：`All normal providers failed, trying fallback group`

---

## TC-008 熔断器触发（认证失败）

**验证**：认证失败立即熔断，禁用 7 天

前置：将 exa 的 `api_key` 改为无效值。

```bash
sg search "test circuit 1"
sg status
```

预期：
- 第一次失败后熔断器即打开
- `sg status` 显示 `exa-1: [open], reason=auth, retry in ~604800s`
- 日志：`Circuit breaker OPENED: failure_type=auth, timeout=168.0h`

---

## TC-009 熔断器恢复

**验证**：修复 key 后，健康检查重置熔断器

前置：接 TC-008，恢复正确的 api_key。

```bash
sg health
sg search "test recovery"
```

预期：
- `sg health` 显示 exa-1 恢复
- 日志：`Circuit breaker manually reset to CLOSED state`
- 后续搜索重新使用 exa-1

---

## TC-013 DEBUG 日志完整性

**验证**：日志包含完整执行链路

```bash
sg search "test debug"
cat ~/.sg/logs/test.log | grep -E "(Executing|Candidate|Trying|Selecting|Selected|succeeded|completed|History saved)"
```

预期日志链路：
```
Executing search request, provider=auto
Candidate groups: [...]
Trying group: exa
Selecting instance from group 'exa'...
Selected instance: exa-1
Provider exa-1 succeeded in Xms
Request completed: provider=exa-1
History saved: ...
```

---

## TC-018 网关状态查询

**验证**：`sg status` 展示完整状态

```bash
sg status
```

预期包含：
- `Running: True`
- Provider 列表
- 每实例指标（请求数、成功率、延迟、熔断器状态）

---

## TC-019 Provider 列表

```bash
sg providers
```

预期：显示每个 provider 的 capabilities、search_params、priority。

---

## TC-022 特殊字符查询

```bash
sg search "test \"quotes\" and 'apostrophes'"
```

预期：正常返回结果，不崩溃，不注入。

---

## TC-023 全量功能测试（Search / Extract / Research）

```bash
# Search
sg search "python programming"

# Extract
sg extract "https://docs.python.org/3/tutorial/index.html"

# Research
sg research "artificial intelligence trends 2026"
```

预期：三个命令均成功返回结果文件。
