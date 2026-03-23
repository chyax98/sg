# 配置设计对比：v3.0 vs v3.1

## 场景：3 个 Tavily API Key

### v3.0 配置（当前）

```json
{
  "providers": {
    "tavily-1": {
      "type": "tavily",
      "api_key": "tvly-key-1",
      "priority": 1
    },
    "tavily-2": {
      "type": "tavily",
      "api_key": "tvly-key-2",
      "priority": 1
    },
    "tavily-3": {
      "type": "tavily",
      "api_key": "tvly-key-3",
      "priority": 2
    }
  }
}
```

**问题：**
- 重复的 `type: "tavily"`
- 无法区分"类别配置"和"实例配置"
- 所有 instances 共享相同的策略
- 配置冗余

---

### v3.1 配置（新设计）

```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "capabilities": ["search", "extract", "research"],
      "base_url": "https://api.tavily.com",
      "timeout": 30000,
      "selection": {
        "strategy": "round_robin",
        "retry_on_empty": true
      }
    }
  },
  "instances": {
    "tavily-1": {
      "provider": "tavily",
      "api_key": "tvly-key-1",
      "priority": 1
    },
    "tavily-2": {
      "provider": "tavily",
      "api_key": "tvly-key-2",
      "priority": 1
    },
    "tavily-3": {
      "provider": "tavily",
      "api_key": "tvly-key-3",
      "priority": 2
    }
  }
}
```

**优势：**
- 通用配置提取到 Provider 级别
- Instances 只包含差异化配置（api_key, priority）
- 可以为每个 Provider 配置不同的策略
- 更清晰的分层

---

## 运行时行为对比

### 场景：调用 search("AI news")

#### v3.0 行为

```
1. Executor 看到 3 个独立的 providers: tavily-1, tavily-2, tavily-3
2. 按 priority 排序: [tavily-1, tavily-2, tavily-3]
3. 尝试 tavily-1 → 失败
4. 尝试 tavily-2 → 成功
5. 返回结果

问题：
- 把同一个 provider 的多个 key 当作不同的 providers
- 无法做 instance 级别的随机选择
- failover 逻辑跨越不同 provider types
```

#### v3.1 行为

```
1. Executor 看到 1 个 Provider "tavily"
2. ProviderPool 管理 3 个 instances
3. 按 selection.strategy = "round_robin" 选择:
   - 第 1 次请求: tavily-1
   - 第 2 次请求: tavily-2
   - 第 3 次请求: tavily-3
   - 第 4 次请求: tavily-1 (循环)
4. 如果选中的 instance 失败，同 provider 内选择下一个
5. 如果所有 instances 都失败，failover 到其他 providers

优势：
- 负载均衡在同一个 provider 内部完成
- 清晰的层级：Provider Pool → Instance
- 可以配置不同的选择策略
```

---

## 配置项对比

| 配置项 | v3.0 | v3.1 Provider | v3.1 Instance |
|-------|------|---------------|---------------|
| type | ✅ 每个 instance | ✅ 一次定义 | ❌ 继承 |
| api_key | ✅ 每个 instance | ❌ 不在这里 | ✅ 每个 instance |
| base_url | ❌ 硬编码 | ✅ 可配置 | ❌ 继承 |
| timeout | ❌ 硬编码 | ✅ 可配置 | ❌ 继承 |
| capabilities | ❌ ProviderInfo | ✅ 可覆盖 | ❌ 继承 |
| priority | ✅ 每个 instance | ❌ 不在这里 | ✅ 每个 instance |
| selection.strategy | ❌ 全局统一 | ✅ 每个 provider | ❌ 继承 |
| enabled | ✅ 每个 instance | ✅ 总开关 | ✅ 每个 instance |

---

## 代码实现对比

### v3.0 Executor

```python
class Executor:
    def _candidates(self, capability, provider=None):
        # 所有 instances 平铺处理
        providers = self.registry.get_by_capability(capability)
        # 返回: [tavily-1, tavily-2, tavily-3, brave-1, exa-1, ...]
        # 问题：无法区分 tavily-1/2/3 是同一个 provider
```

### v3.1 Executor

```python
class Executor:
    def execute(self, capability, operation, provider=None):
        if provider:
            # 先尝试指定 provider
            pool = self.registry.get_pool(provider)
            result = await self._try_pool(pool, operation)
            if result.success:
                return result
        
        # 按顺序尝试其他 providers
        for pool in self.registry.get_pools_by_capability(capability):
            if pool.name == provider:
                continue  # 已经尝试过
            result = await self._try_pool(pool, operation)
            if result.success:
                return result
    
    async def _try_pool(self, pool: ProviderPool, operation):
        # Pool 内部处理 instance 选择
        instance = pool.select()
        if not instance:
            return FailedResult("No available instance")
        
        try:
            return await operation(instance)
        except Exception as e:
            # 同 pool 内 failover
            next_instance = pool.select(exclude=[instance.name])
            if next_instance:
                return await operation(next_instance)
            raise
```

---

## 选择策略对比

### v3.0：全局策略

```json
{
  "executor": {
    "strategy": "round_robin"  // 影响所有 providers
  }
}
```

### v3.1：Provider 级别策略

```json
{
  "providers": {
    "tavily": {
      "selection": {
        "strategy": "round_robin"  // Tavily 内部轮询
      }
    },
    "exa": {
      "selection": {
        "strategy": "random"  // Exa 内部随机
      }
    },
    "brave": {
      "selection": {
        "strategy": "priority"  // Brave 按优先级
      }
    }
  }
}
```

---

## 可视化对比

### v3.0 结构

```
Registry
├── tavily-1 (type=tavily)
├── tavily-2 (type=tavily)
├── tavily-3 (type=tavily)
├── brave-1 (type=brave)
└── exa-1 (type=exa)

平铺结构，无法识别 tavily-1/2/3 的关系
```

### v3.1 结构

```
Registry
├── Pool: tavily
│   ├── Instance: tavily-1
│   ├── Instance: tavily-2
│   └── Instance: tavily-3
├── Pool: brave
│   └── Instance: brave-1
└── Pool: exa
    ├── Instance: exa-1
    └── Instance: exa-2

层级结构，清晰的 Pool → Instance 关系
```

---

## 迁移成本

### 自动迁移

```python
# 一键迁移脚本
sg config migrate --from 3.0 --to 3.1

# 或启动时自动检测并迁移
sg start
# 检测到 v3.0 配置，自动迁移到 v3.1...
# 备份原配置到 config.json.v3.0.backup
```

### 向后兼容

- v3.1 代码可以读取 v3.0 配置（自动迁移）
- 但 v3.0 代码无法读取 v3.1 配置
- 建议升级后不再回退

---

## 决策建议

| 如果你... | 建议 |
|----------|------|
| 只有 1-2 个 providers | v3.0 够用，但 v3.1 更清晰 |
| 有多个相同 provider 的 keys | **强烈建议 v3.1** |
| 需要不同的 instance 选择策略 | **必须使用 v3.1** |
| 需要 instance 级别的熔断 | **必须使用 v3.1** |
| 希望配置更清晰 | **建议使用 v3.1** |
