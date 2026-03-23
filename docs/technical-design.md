# Search Gateway 技术设计文档

## 1. 核心架构

### 1.1 组件关系

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │   CLI   │  │ HTTP API│  │   SDK   │  │   MCP Server    │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘ │
│       └─────────────┴─────────────┴────────────────┘         │
│                         │                                    │
└─────────────────────────┼────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                          Gateway                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  search() / extract() / research()                     │  │
│  │  └── 构建 Request + Operation                          │  │
│  │       └── Executor.execute(capability, operation,      │  │
│  │                    provider?)  ← 可选指定               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                         Executor                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _candidates(capability, provider?)                    │  │
│  │  ├── 指定 provider?                                    │  │
│  │  │   ├── 插入队首                                       │  │
│  │  │   └── 其余按策略排序                                 │  │
│  │  └── 未指定?                                           │  │
│  │      └── 按策略选择                                     │  │
│  │                                                        │  │
│  │  execute()                                            │  │
│  │  ├── 尝试 candidate[0]                                │  │
│  │  ├── 失败/空结果? → 尝试 candidate[1]                  │  │
│  │  ├── ...                                              │  │
│  │  └── 全部失败 → fallback → 报错                       │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────┼───────────────────────────────┐  │
│  │                       ▼                               │  │
│  │  CircuitBreaker (per provider)                        │  │
│  │  ├── CLOSED: 正常服务                                  │  │
│  │  ├── OPEN: 熔断跳过                                    │  │
│  │  └── HALF_OPEN: 探测恢复                               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────┬────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Provider Registry                        │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────────┐ │
│  │ Tavily  │ │  Brave  │ │   Exa   │ │     DuckDuckGo      │ │
│  │ (multi) │ │ (multi) │ │ (multi) │ │    (fallback)       │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 关键类定义

```python
# Executor 核心逻辑
class Executor:
    def _candidates(self, capability: str, provider: str | None) -> list[str]:
        """
        构建候选 provider 列表
        
        逻辑:
        1. 如果指定 provider:
           - 检查是否存在且支持该 capability
           - 插入列表头部
           - 其余 providers 按策略排序
        2. 如果未指定:
           - 按策略选择可用 providers
        3. 最后添加 fallback (如果不在列表中)
        """
        
    async def execute(self, capability, operation, provider=None) -> Result:
        """
        执行操作，支持 failover
        
        逻辑:
        1. 获取 candidates
        2. 按顺序尝试，直到成功
        3. 记录每个 candidate 的结果状态
        4. 返回成功结果 + 尝试历史
        """
```

## 2. 关键行为详细设计

### 2.1 指定 Provider 的 Failover 链路

```python
# 场景 1: 指定存在的 provider
candidates = executor._candidates("search", provider="tavily-main")
# 返回: ["tavily-main", "brave-1", "exa-1", "duckduckgo"]

# 场景 2: 指定的 provider 被熔断
candidates = executor._candidates("search", provider="tavily-main")
# 如果 tavily-main 熔断:
# 返回: ["brave-1", "exa-1", "duckduckgo"] (tavily-main 被跳过)

# 场景 3: 指定的 provider 不支持该 capability
candidates = executor._candidates("extract", provider="brave-1")
# Brave 不支持 extract:
# 警告日志 + 回退到自动选择

# 场景 4: 指定的 provider 不存在
candidates = executor._candidates("search", provider="unknown")
# 警告日志 + 回退到自动选择
```

### 2.2 空结果处理

```python
# 当前行为: 返回空结果即成功
# 新行为: 空结果可配置为触发 failover

class ExecutorConfig:
    empty_result_failover: bool = True  # 空结果继续尝试
    
async def _try_provider(self, name, provider, operation):
    result = await operation(provider)
    
    # 检查是否为空结果
    if self._is_empty_result(result):
        if self.config.empty_result_failover:
            logger.info(f"Provider {name} returned empty result, will failover")
            # 记录为"需要继续"而不是失败
            return False, result, EmptyResultError()
        else:
            return True, result, None
    
    return True, result, None
```

### 2.3 结果包装

```python
class SearchResultWithMeta(SearchResponse):
    """包含执行元数据的搜索结果"""
    attempted_providers: list[AttemptInfo]
    
class AttemptInfo:
    provider: str
    status: "success" | "empty" | "failed" | "skipped"
    latency_ms: float
    error_type: str | None  # 失败时的错误类型
```

## 3. 配置设计

### 3.1 新增配置项

```json
{
  "executor": {
    "strategy": "round_robin",
    "failover": {
      "max_attempts": 3,
      "empty_result_failover": true
    },
    "circuit_breaker": {
      "failure_threshold": 3,
      "success_threshold": 2,
      "base_timeout": 3600,
      "multiplier": 6,
      "max_timeout": 172800
    }
  }
}
```

### 3.2 Provider 优先级配置

```json
{
  "providers": {
    "tavily-main": {
      "type": "tavily",
      "priority": 1,
      "empty_result_failover": true
    },
    "brave-1": {
      "type": "brave", 
      "priority": 2,
      "empty_result_failover": true
    }
  }
}
```

## 4. API 设计

### 4.1 HTTP API

```http
POST /search
Content-Type: application/json

{
  "query": "MCP protocol",
  "provider": "tavily",  // 可选，指定优先尝试的 provider
  "max_results": 10,
  "include_domains": ["github.com"]
}
```

响应:
```json
{
  "query": "MCP protocol",
  "provider": "brave",  // 实际使用的 provider
  "results": [...],
  "total": 10,
  "latency_ms": 850,
  "meta": {
    "attempted": [
      {"provider": "tavily", "status": "failed", "error": "quota_exceeded", "latency_ms": 120},
      {"provider": "brave", "status": "success", "latency_ms": 730}
    ]
  }
}
```

### 4.2 MCP Tool

```typescript
// search 工具保持不变，但内部行为更新
{
  name: "search",
  parameters: {
    query: string,
    provider?: string,  // 新增可选参数
    max_results?: number
  }
}
```

## 5. 实现计划

### Phase 1: 核心 Failover
- [ ] 修改 `_candidates()` 支持指定 provider
- [ ] 修改 `execute()` 记录尝试历史
- [ ] 更新结果模型包含元数据

### Phase 2: 空结果处理
- [ ] 添加空结果检测逻辑
- [ ] 添加配置项 `empty_result_failover`
- [ ] 更新各 provider 的空结果判断

### Phase 3: 观测性
- [ ] 在响应中返回尝试历史
- [ ] 更新状态页面显示尝试链路
- [ ] 添加相关 metrics

## 6. 边界情况处理

| 场景 | 行为 |
|------|------|
| 指定 provider 成功 | 返回结果，记录尝试历史 |
| 指定 provider 失败 | 继续 failover，返回后续成功的结果 |
| 指定 provider 熔断 | 跳过它，直接 failover |
| 指定 provider 空结果 | 继续 failover（如果配置启用） |
| 所有 provider 失败 | 返回错误，包含完整尝试历史 |
| 指定不存在的 provider | 警告日志，回退到自动选择 |
| 指定不支持 capability 的 provider | 警告日志，回退到自动选择 |

## 7. 与现有设计的兼容性

- 不指定 provider 时，行为完全不变
- 现有配置无需修改即可工作
- 新增配置项都有默认值
- API 新增字段都是可选的
