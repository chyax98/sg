# Search Gateway 黑盒测试用例

## 测试环境
- 网关地址：http://127.0.0.1:8100
- 日志级别：DEBUG
- 日志文件：~/.sg/logs/gateway.log

---

## 1. 基础功能测试

### TC-001: 单个搜索请求
**目的**：验证基本搜索功能
**步骤**：
```bash
sg search "python async"
```
**预期结果**：
- 返回搜索结果文件路径
- 文件包含搜索结果
- 使用最高优先级的 Provider（exa-1）

### TC-002: 批量搜索请求
**目的**：验证批量搜索并行执行
**步骤**：
```bash
sg search "python" "rust" "go"
```
**预期结果**：
- 返回 3 个搜索结果文件路径
- 并行执行（日志显示几乎同时开始）
- 可能使用不同的 Provider 实例

### TC-003: 指定 Provider 搜索
**目的**：验证指定 Provider 功能
**步骤**：
```bash
sg search "test" -p tavily
```
**预期结果**：
- 使用 tavily Group 的实例
- 不尝试其他 Provider

---

## 2. 优先级测试

### TC-004: Provider 绝对优先级
**目的**：验证 Provider Group 的绝对优先级
**步骤**：
```bash
sg search "test1"
sg search "test2"
sg search "test3"
```
**预期结果**：
- 所有请求都从 exa (priority=1) 开始
- 日志显示：Candidate groups: ['exa', 'tavily', 'youcom']
- 日志显示：Trying group: exa

### TC-005: Instance 选择策略
**目的**：验证 Instance 级别的 Round Robin
**步骤**：
1. 配置 tavily 的 selection 为 "round_robin"
2. 禁用 exa，强制使用 tavily
3. 执行 3 次搜索
**预期结果**：
- 轮流使用 tavily-2 和 tavily-3
- 不会总是使用同一个实例

---

## 3. 故障转移测试

### TC-006: Provider 故障转移
**目的**：验证 Provider 失败后自动切换
**步骤**：
1. 配置一个无效的 API Key 给 exa
2. 执行搜索
**预期结果**：
- exa 失败后自动尝试 tavily
- 日志显示：Provider exa-1 failed
- 日志显示：Trying group: tavily
- 最终使用 tavily 成功

### TC-007: 所有 Provider 失败
**目的**：验证所有 Provider 失败后使用 Fallback
**步骤**：
1. 配置所有 Provider 的 API Key 为无效值
2. 执行搜索
**预期结果**：
- 尝试所有正常 Provider 后失败
- 最后尝试 Fallback Provider (duckduckgo)
- 日志显示：All normal providers failed, trying fallback group

---

## 4. 熔断器测试

### TC-008: 熔断器触发（临时错误）
**目的**：验证连续失败触发熔断器
**步骤**：
1. 配置 exa 的 API Key 为无效值
2. 执行 3 次搜索（触发熔断阈值）
3. 查看熔断器状态
**预期结果**：
- 前 3 次失败后，熔断器打开
- 日志显示：Circuit breaker OPENED: failure_type=auth
- sg status 显示 exa-1 的 circuit_breaker 状态为 "open"

### TC-009: 熔断器恢复
**目的**：验证熔断器自动恢复
**步骤**：
1. 修复 exa 的 API Key
2. 执行健康检查
3. 再次搜索
**预期结果**：
- 健康检查成功后，熔断器重置
- 日志显示：Circuit breaker manually reset to CLOSED state
- 后续搜索可以使用 exa

### TC-010: 配额耗尽熔断
**目的**：验证 429 错误触发配额熔断
**步骤**：
1. 使用一个配额已耗尽的 API Key
2. 执行搜索
**预期结果**：
- 日志显示：Provider xxx: quota exceeded, disabled for 24h
- 日志显示：Circuit breaker OPENED: failure_type=quota
- 熔断器禁用 24 小时

---

## 5. 自动启动测试

### TC-011: 自动启动网关
**目的**：验证网关未运行时自动启动
**步骤**：
```bash
sg stop
sg search "test auto start"
```
**预期结果**：
- 网关自动在后台启动
- 等待网关就绪后执行搜索
- 搜索成功返回结果

### TC-012: 网关已运行时不重复启动
**目的**：验证网关已运行时不重复启动
**步骤**：
```bash
sg search "test1"
sg search "test2"
```
**预期结果**：
- 第二次搜索不会尝试启动网关
- 直接使用已运行的网关

---

## 6. 日志测试

### TC-013: DEBUG 日志级别
**目的**：验证 DEBUG 日志输出完整信息
**步骤**：
```bash
sg stop
sg start --log-level DEBUG --log-file ~/.sg/logs/gateway.log &
sleep 3
sg search "test debug"
tail -50 ~/.sg/logs/gateway.log
```
**预期结果**：
- 日志包含：Executing search request
- 日志包含：Candidate groups
- 日志包含：Trying group
- 日志包含：Selecting instance from group
- 日志包含：Selected instance
- 日志包含：Provider xxx succeeded
- 日志包含：Request completed
- 日志包含：History saved

### TC-014: INFO 日志级别
**目的**：验证 INFO 日志只输出关键信息
**步骤**：
```bash
sg stop
sg start --log-level INFO --log-file ~/.sg/logs/gateway.log &
sleep 3
sg search "test info"
tail -50 ~/.sg/logs/gateway.log
```
**预期结果**：
- 日志包含：Executing search request
- 日志包含：Provider xxx succeeded
- 日志包含：Request completed
- 日志不包含：Candidate groups（DEBUG 级别）
- 日志不包含：Selecting instance（DEBUG 级别）

---

## 7. History 测试

### TC-015: History 记录保存
**目的**：验证搜索历史正确保存
**步骤**：
```bash
sg search "test history"
ls -la ~/.sg/history/$(date +%Y-%m)/
```
**预期结果**：
- 在当前月份目录下生成 JSON 文件
- 文件名格式：YYYYMMDD-HHMMSS-xxxxxx.json
- 文件包含完整的搜索结果

### TC-016: History 查看
**目的**：验证历史记录查看功能
**步骤**：
```bash
sg history
```
**预期结果**：
- 显示最近的搜索历史
- 包含 query、provider、结果数、时间戳

### TC-017: History 清空
**目的**：验证历史记录清空功能
**步骤**：
```bash
sg history --clear
```
**预期结果**：
- 删除所有历史记录文件
- 返回删除的记录数

---

## 8. 状态和监控测试

### TC-018: 网关状态查询
**目的**：验证状态查询功能
**步骤**：
```bash
sg status
```
**预期结果**：
- 显示网关运行状态
- 显示可用 Provider 列表
- 显示执行指标（请求数、成功率、平均延迟）
- 显示熔断器状态

### TC-019: Provider 列表查询
**目的**：验证 Provider 列表功能
**步骤**：
```bash
sg providers
```
**预期结果**：
- 显示所有配置的 Provider
- 显示每个 Provider 的能力
- 显示优先级信息

---

## 9. 边界测试

### TC-020: 空查询
**目的**：验证空查询处理
**步骤**：
```bash
sg search ""
```
**预期结果**：
- 返回错误或空结果
- 不会崩溃

### TC-021: 超长查询
**目的**：验证超长查询处理
**步骤**：
```bash
sg search "$(python3 -c 'print("a" * 10000)')"
```
**预期结果**：
- 正常处理或返回错误
- 不会崩溃

### TC-022: 特殊字符查询
**目的**：验证特殊字符处理
**步骤**：
```bash
sg search "test \"quotes\" and 'apostrophes'"
sg search "test <html> & symbols"
```
**预期结果**：
- 正确处理特殊字符
- 不会导致注入或崩溃

---

## 10. 性能测试

### TC-023: 并发搜索性能
**目的**：验证并发处理能力
**步骤**：
```bash
for i in {1..10}; do sg search "test$i" & done
wait
```
**预期结果**：
- 所有请求都成功完成
- 没有超时或崩溃
- 负载均衡到不同的 Provider 实例

### TC-024: 大批量搜索
**目的**：验证批量搜索性能
**步骤**：
```bash
sg search "query1" "query2" "query3" "query4" "query5"
```
**预期结果**：
- 所有查询并行执行
- 总耗时接近单个查询的耗时
- 所有结果都正确返回

---

## 测试执行计划

### 阶段 1：基础功能（TC-001 ~ TC-003）
- 验证基本搜索、批量搜索、指定 Provider

### 阶段 2：优先级和故障转移（TC-004 ~ TC-007）
- 验证优先级逻辑、故障转移机制

### 阶段 3：熔断器（TC-008 ~ TC-010）
- 验证熔断器触发、恢复、不同错误类型

### 阶段 4：自动启动和日志（TC-011 ~ TC-014）
- 验证自动启动、日志输出

### 阶段 5：History 和状态（TC-015 ~ TC-019）
- 验证历史记录、状态查询

### 阶段 6：边界和性能（TC-020 ~ TC-024）
- 验证边界情况、性能表现

---

## 测试结果记录

| 用例编号 | 用例名称 | 状态 | 备注 |
|---------|---------|------|------|
| TC-001 | 单个搜索请求 | | |
| TC-002 | 批量搜索请求 | | |
| TC-003 | 指定 Provider 搜索 | | |
| TC-004 | Provider 绝对优先级 | | |
| TC-005 | Instance 选择策略 | | |
| TC-006 | Provider 故障转移 | | |
| TC-007 | 所有 Provider 失败 | | |
| TC-008 | 熔断器触发 | | |
| TC-009 | 熔断器恢复 | | |
| TC-010 | 配额耗尽熔断 | | |
| TC-011 | 自动启动网关 | | |
| TC-012 | 网关已运行时不重复启动 | | |
| TC-013 | DEBUG 日志级别 | | |
| TC-014 | INFO 日志级别 | | |
| TC-015 | History 记录保存 | | |
| TC-016 | History 查看 | | |
| TC-017 | History 清空 | | |
| TC-018 | 网关状态查询 | | |
| TC-019 | Provider 列表查询 | | |
| TC-020 | 空查询 | | |
| TC-021 | 超长查询 | | |
| TC-022 | 特殊字符查询 | | |
| TC-023 | 并发搜索性能 | | |
| TC-024 | 大批量搜索 | | |
