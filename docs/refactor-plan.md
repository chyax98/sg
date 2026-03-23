# Search Gateway 重构方案

## 一、需求整理

### 1.1 用户核心诉求

**简化原则**：
- 不要过度设计
- 逻辑清晰易懂
- 配置项最小化
- 避免不必要的复杂度

**核心能力**：
- Search（快捷搜索）
- GetContent（网页抓取）
- Research（深度研究）

### 1.2 配置管理需求

**配置文件存放**：
- 默认路径：`~/.sg/config.json`
- 支持自定义路径
- 用户目录下独立文件夹

**配置方式**：
1. **Web UI**（主要方式）
   - 可视化添加 Provider
   - 多行输入 API Key
   - 部分 Provider 需要手动输入 URL

2. **CLI**（Linux 支持）
   - `sg config add-provider <type>`
   - `sg config set-key <provider> <key>`
   - `sg config list`

### 1.3 调度策略需求

**核心流程**：
```
1. 加载配置 → 按 capability 筛选 providers
2. Fallback provider 不加载到常规池
3. 按优先级排序 Provider（priority 从小到大）
4. 从第一个 Provider 随机选一个 Instance
5. Instance 失败 → 尝试同 Provider 下其他 Instance
6. Provider 下所有 Instance 都失败 → 进入下一个 Provider
7. 所有 Provider 都失败 → 尝试 Fallback（仅 search）
8. Fallback 也失败 → 返回错误
```

**禁用机制**：
- Instance 持续失败 → 自动禁用（Circuit Breaker）
- Provider 下所有 Instance 都禁用 → 该 Provider 被跳过
- 状态页能看到 Provider 级别的禁用状态

**空结果处理**（可选）：
- 如果返回空结果，继续尝试下一个 Provider
- 直到拿到有内容的结果，或所有 Provider 都试完

---

## 二、当前实现分析

### 2.1 已经实现的功能

✅ **核心调度逻辑**：
- 按 capability 筛选 providers
- 按 priority 排序 provider groups
- 同 group 内 instance 失败后尝试其他 instance
- Circuit breaker 实现禁用机制
- Fallback 按 capability 配置（刚完成重构）

✅ **配置模型**：
- Provider group + instances 结构
- 支持多种 selection 策略
- 支持 fallback_for 配置

✅ **API 接口**：
- Config API（PUT/DELETE endpoints）
- Status API
- Metrics API

### 2.2 存在的问题

❌ **策略过于复杂**：
- 外层策略：failover / round_robin / random（3 种）
- 内层策略：random / round_robin / priority（3 种）
- 用户只需要：外层按 priority，内层随机选择

❌ **缺失功能**：
- 没有 Web UI 配置界面
- CLI 只能查看，不能配置
- 没有空结果重试功能
- Provider 级别禁用状态不明显

❌ **并发安全问题**：
- Round robin 索引不是线程安全的

---

## 三、重构方案

### 3.1 简化策略配置

**目标**：去掉不必要的策略选项，固定为最常用的组合。

**方案 A：完全简化（推荐）**

删除 `executor.strategy` 和 `providers.<group>.selection` 配置项，固定为：
- 外层：按 priority 顺序尝试（failover）
- 内层：随机选择（random）

配置简化为：
```json
{
  "providers": {
    "exa": {
      "type": "exa",
      "priority": 1,  // 只保留 priority
      "instances": [...]
    }
  }
}
```

**方案 B：保留但简化（折中）**

保留配置项，但设置更好的默认值，并在文档中明确推荐：
```json
{
  "executor": {
    "strategy": "failover"  // 默认值，推荐不改
  },
  "providers": {
    "exa": {
      "selection": "random"  // 默认值，推荐不改
    }
  }
}
```

**建议**：采用方案 A，彻底简化。

### 3.2 新增空结果重试

**配置**：
```json
{
  "executor": {
    "retry_on_empty_results": false,  // 默认关闭
    "min_results_threshold": 1        // 至少多少条结果才算成功
  }
}
```

**逻辑**：
```python
async def _try_provider(...):
    result = await operation(provider)

    # 检查是否为空结果
    if self.config.retry_on_empty_results:
        if hasattr(result, 'results') and len(result.results) < self.config.min_results_threshold:
            return False, result, EmptyResultsError()

    return True, result, None
```

### 3.3 改进状态展示

**Provider 级别状态**：

在 `/providers` 接口返回中增加 `group_status` 字段：

```json
{
  "providers": [
    {
      "group": "exa",
      "group_status": "healthy",  // healthy / degraded / disabled
      "instances": [
        {"id": "exa-1", "status": "healthy"},
        {"id": "exa-2", "status": "disabled"}
      ]
    }
  ]
}
```

状态判断逻辑：
- `healthy`: 至少有一个 instance 可用
- `degraded`: 部分 instance 被禁用
- `disabled`: 所有 instance 都被禁用

### 3.4 配置管理 UI（后续）

**Web UI**：
- 在现有 Web UI 基础上增加配置页面
- 表单添加 Provider
- 多行文本框输入 API Keys
- 实时验证 API Key 有效性

**CLI**：
```bash
sg config add-provider exa --key "xxx"
sg config add-instance exa exa-2 --key "yyy"
sg config remove-provider exa
sg config list
sg config show exa
```

---

## 四、实施计划

### Phase 1：核心简化（优先）

**任务 1.1：简化策略配置**
- [ ] 删除 `executor.strategy` 配置项
- [ ] 删除 `providers.<group>.selection` 配置项
- [ ] 固定为：外层 failover，内层 random
- [ ] 更新配置模型和文档

**任务 1.2：修复并发安全问题**
- [ ] 为 round_robin 索引加锁（如果保留）
- [ ] 或者删除 round_robin 策略（如果采用方案 A）

**任务 1.3：改进状态展示**
- [ ] 增加 Provider 级别状态判断
- [ ] 更新 `/providers` API 返回格式
- [ ] 更新状态页展示

### Phase 2：功能增强（可选）

**任务 2.1：空结果重试**
- [ ] 增加 `retry_on_empty_results` 配置
- [ ] 实现空结果检测逻辑
- [ ] 增加测试用例

**任务 2.2：错误分类优化**
- [ ] 新增 PERMANENT 错误类型
- [ ] 优化 400/404 等错误的处理
- [ ] 避免无意义重试

### Phase 3：配置管理 UI（后续）

**任务 3.1：Web UI**
- [ ] 设计配置页面
- [ ] 实现 Provider 添加表单
- [ ] 实现 API Key 验证

**任务 3.2：CLI**
- [ ] 实现 `sg config` 子命令
- [ ] 支持添加/删除/查看配置
- [ ] 支持交互式配置向导

---

## 五、配置文件示例

### 5.1 简化后的配置

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8100
  },
  "providers": {
    "exa": {
      "type": "exa",
      "enabled": true,
      "priority": 1,
      "instances": [
        {"id": "exa-1", "api_key": "xxx"},
        {"id": "exa-2", "api_key": "yyy"}
      ]
    },
    "tavily": {
      "type": "tavily",
      "priority": 2,
      "instances": [
        {"id": "tavily-1", "api_key": "zzz"}
      ]
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "priority": 100,
      "fallback_for": ["search"],
      "instances": [
        {"id": "duckduckgo"}
      ]
    }
  },
  "executor": {
    "retry_on_empty_results": false,
    "min_results_threshold": 1,
    "circuit_breaker": {
      "base_timeout": 7200,
      "multiplier": 3,
      "max_timeout": 172800,
      "quota_timeout": 86400,
      "auth_timeout": 604800
    },
    "failover": {
      "max_attempts": 3
    }
  }
}
```

### 5.2 配置说明

**Provider 配置**：
- `type`: Provider 类型（必填）
- `enabled`: 是否启用（默认 true）
- `priority`: 优先级，数字越小越优先（必填）
- `fallback_for`: 作为哪些 capability 的 fallback（可选）
- `instances`: 实例列表（必填）

**Instance 配置**：
- `id`: 实例 ID（必填，唯一）
- `enabled`: 是否启用（默认 true）
- `api_key`: API Key（部分 provider 必填）
- `url`: 自定义 URL（部分 provider 可选）
- `timeout`: 超时时间（可选，继承 defaults）

**Executor 配置**：
- `retry_on_empty_results`: 空结果重试（默认 false）
- `min_results_threshold`: 最少结果数（默认 1）
- `circuit_breaker`: 断路器配置
- `failover.max_attempts`: 最多尝试几个 provider groups

---

## 六、调度流程图

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 请求进入 Gateway.search(query)                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Executor.execute(capability="search", operation)         │
│    - 按 capability 筛选 providers                            │
│    - 排除 fallback providers                                 │
│    - 按 priority 排序（从小到大）                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 遍历 Provider Groups（最多 max_attempts 个）             │
│    for group in groups[:max_attempts]:                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Registry.select_instance(group, capability)              │
│    - 筛选支持该 capability 的 instances                      │
│    - 过滤掉被 circuit breaker 禁用的                         │
│    - 随机选择一个 instance                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. 执行请求 provider.search(request)                         │
│    - 应用 timeout                                            │
│    - 记录 metrics                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    成功 / 失败？
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
    【成功】                            【失败】
        ↓                                   ↓
  breaker.record_success()        breaker.record_failure()
        ↓                                   ↓
  返回结果 ✓                      同 group 内还有其他 instance？
                                            ↓
                                    ┌───────┴───────┐
                                    ↓               ↓
                                  【有】          【没有】
                                    ↓               ↓
                            重新 select_instance   进入下一个 group
                                    ↓
                                  重试

                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. 所有 groups 都失败？                                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    ┌─────┴─────┐
                    ↓           ↓
                 【是】       【否】
                    ↓           ↓
            尝试 fallback   返回结果 ✓
                    ↓
        Registry.get_fallback_group(capability)
                    ↓
            有 fallback？
                    ↓
            ┌───────┴───────┐
            ↓               ↓
          【有】          【没有】
            ↓               ↓
      重复步骤 4-5      返回错误 ✗
            ↓
      fallback 成功？
            ↓
      ┌─────┴─────┐
      ↓           ↓
    【是】       【否】
      ↓           ↓
  返回结果 ✓   返回错误 ✗
```

---

## 七、总结

### 7.1 核心改进

1. **简化策略**：去掉复杂的策略配置，固定为最常用的组合
2. **改进展示**：Provider 级别状态更清晰
3. **新增功能**：空结果重试（可选）
4. **修复问题**：并发安全、错误分类

### 7.2 保持不变

1. **核心架构**：两层路由（group → instance）
2. **Circuit Breaker**：实例级熔断机制
3. **Fallback 机制**：按 capability 配置
4. **配置结构**：Provider group + instances

### 7.3 后续规划

1. **配置管理 UI**：Web UI + CLI
2. **更多优化**：性能优化、监控增强
3. **文档完善**：用户指南、最佳实践

---

## 八、决策点

需要用户确认的关键决策：

1. **是否完全删除策略配置项？**
   - 方案 A：完全删除，固定为 failover + random
   - 方案 B：保留但设置默认值

2. **是否实现空结果重试？**
   - 如果实现，默认开启还是关闭？

3. **配置管理 UI 的优先级？**
   - Phase 1 就做，还是 Phase 3 再做？

4. **是否需要保留 round_robin 策略？**
   - 如果不需要，可以删除相关代码
   - 如果需要，需要修复并发安全问题
