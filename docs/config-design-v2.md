# Search Gateway 配置设计 v2.0

## 核心思想

> **Provider = 类别，Instance = 具体配置**

```
Provider (类别)
├── 通用配置 (shared config)
│   ├── base_url
│   ├── timeout
   ├── capabilities
│   └── rate_limit
│
└── Instances (实例列表)
    ├── instance-1 (api_key_1)
    ├── instance-2 (api_key_2)
    └── instance-3 (api_key_3)
```

## 配置层级

### 1. Provider 级别配置（通用）

```json
{
  "providers": {
    "exa": {
      "type": "exa",
      "enabled": true,
      "capabilities": ["search", "extract"],
      "base_url": "https://api.exa.ai",
      "timeout": 30000,
      "rate_limit": {
        "requests_per_minute": 100
      },
      "features": {
        "include_domains": true,
        "exclude_domains": true,
        "time_range": true
      },
      "selection": {
        "strategy": "random",
        "retry_on_empty": true
      }
    }
  }
}
```

### 2. Instance 级别配置（差异化）

```json
{
  "instances": {
    "exa-main": {
      "provider": "exa",
      "enabled": true,
      "api_key": "exa-key-1",
      "priority": 1,
      "labels": ["production"]
    },
    "exa-backup": {
      "provider": "exa",
      "enabled": true,
      "api_key": "exa-key-2",
      "priority": 2,
      "labels": ["backup"]
    },
    "exa-trial": {
      "provider": "exa",
      "enabled": true,
      "api_key": "exa-key-3",
      "priority": 3,
      "labels": ["trial"]
    }
  }
}
```

## 选择策略

### Provider 内实例选择

```python
class ProviderPool:
    """
    同一个 Provider 的多个实例组成一个 Pool
    """
    
    def select_instance(self) -> Instance:
        """
        1. 过滤掉 disabled/fused 的实例
        2. 按 strategy 选择:
           - random: 随机选择
           - round_robin: 轮询
           - priority: 按优先级选择第一个可用的
        3. 返回选中的实例
        """
        available = [
            inst for inst in self.instances
            if inst.enabled and not self.breaker.is_open(inst.name)
        ]
        
        if not available:
            return None
            
        if self.config.selection.strategy == "random":
            return random.choice(available)
        elif self.config.selection.strategy == "round_robin":
            return self._round_robin_select(available)
        elif self.config.selection.strategy == "priority":
            return min(available, key=lambda x: x.priority)
```

### 跨 Provider 选择

```python
class Executor:
    """
    跨 Provider 的 Failover 逻辑
    """
    
    def execute(self, capability, operation, provider: str | None = None):
        """
        执行流程:
        1. 如果指定 provider:
           - 先在该 provider 的 instances 中选择并尝试
           - 如果该 provider 所有 instances 都失败，继续其他 providers
        
        2. 如果未指定 provider:
           - 按全局策略选择 provider
           - 在 provider 内选择 instance
           - 失败则 failover 到下一个 provider
        """
```

## 完整配置示例

```json
{
  "version": "3.1",
  
  "providers": {
    "exa": {
      "type": "exa",
      "enabled": true,
      "capabilities": ["search", "extract"],
      "base_url": "https://api.exa.ai",
      "timeout": 30000,
      "selection": {
        "strategy": "random",
        "retry_on_empty": true,
        "max_retries_per_instance": 1
      },
      "circuit_breaker": {
        "failure_threshold": 3,
        "recovery_timeout": 3600
      }
    },
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "capabilities": ["search", "extract", "research"],
      "base_url": "https://api.tavily.com",
      "timeout": 30000,
      "selection": {
        "strategy": "round_robin",
        "retry_on_empty": true
      }
    },
    "brave": {
      "type": "brave",
      "enabled": true,
      "capabilities": ["search"],
      "base_url": "https://api.search.brave.com",
      "timeout": 10000,
      "selection": {
        "strategy": "priority"
      }
    },
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "capabilities": ["search"],
      "is_fallback": true,
      "selection": {
        "strategy": "random"
      }
    }
  },
  
  "instances": {
    "exa-prod": {
      "provider": "exa",
      "api_key": "exa-prod-key",
      "priority": 1,
      "labels": ["production"]
    },
    "exa-backup": {
      "provider": "exa",
      "api_key": "exa-backup-key",
      "priority": 2,
      "labels": ["backup"]
    },
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
    },
    "brave-main": {
      "provider": "brave",
      "api_key": "brave-key",
      "priority": 1
    }
  },
  
  "execution": {
    "default_strategy": "capability_based",
    "failover": {
      "enabled": true,
      "max_providers": 3,
      "empty_result_failover": true
    },
    "provider_selection": {
      "order": ["exa", "tavily", "brave", "duckduckgo"]
    }
  }
}
```

## 运行时行为

### 场景 1：随机选择 Instance

```
User: search("AI news", provider="exa")

System:
1. 找到 Provider "exa"
2. 获取可用 instances: [exa-prod, exa-backup]
3. Strategy = random → 随机选择 exa-prod
4. 尝试 exa-prod
5. 失败 → 同 provider 内选择 exa-backup
6. 成功 → 返回结果
```

### 场景 2：跨 Provider Failover

```
User: search("AI news")

System:
1. 按 execution.provider_selection.order 选择第一个: exa
2. Provider "exa" 内随机选择 instance: exa-prod
3. exa-prod 失败 → 尝试 exa-backup
4. exa-backup 也失败 → Provider "exa" 标记为不可用
5. Failover 到下一个 Provider: tavily
6. tavily 内 round_robin 选择 instance
7. 成功 → 返回结果
```

### 场景 3：指定 Provider 但允许 Failover

```
User: search("AI news", provider="exa")

System:
1. 优先尝试 Provider "exa"
2. exa 所有 instances 都失败
3. 继续尝试其他 providers (tavily, brave, duckduckgo)
4. 返回实际成功的 provider 和尝试历史
```

## 配置升级方案

### 从 v3.0 升级

```python
# 自动迁移脚本
def migrate_v3_to_v3_1(old_config):
    """
    v3.0:
    {
      "providers": {
        "exa-1": { "type": "exa", "api_key": "key1" },
        "exa-2": { "type": "exa", "api_key": "key2" }
      }
    }
    
    v3.1:
    {
      "providers": {
        "exa": { "type": "exa", "capabilities": [...] }
      },
      "instances": {
        "exa-1": { "provider": "exa", "api_key": "key1" },
        "exa-2": { "provider": "exa", "api_key": "key2" }
      }
    }
    """
    new_config = {
        "version": "3.1",
        "providers": {},
        "instances": {}
    }
    
    # 按 type 分组
    by_type = defaultdict(list)
    for name, cfg in old_config["providers"].items():
        provider_type = cfg.get("type", name)
        by_type[provider_type].append((name, cfg))
    
    # 创建 provider 配置
    for ptype, instances in by_type.items():
        # 从第一个实例推断通用配置
        first = instances[0][1]
        new_config["providers"][ptype] = {
            "type": ptype,
            "enabled": True,
            "capabilities": infer_capabilities(ptype),
            "selection": {
                "strategy": "random"
            }
        }
        
        # 创建 instances
        for name, cfg in instances:
            new_config["instances"][name] = {
                "provider": ptype,
                "api_key": cfg.get("api_key"),
                "priority": cfg.get("priority", 10),
                "enabled": cfg.get("enabled", True)
            }
    
    return new_config
```

## 代码结构

```
src/sg/
├── core/
│   ├── executor.py          # 跨 Provider failover
│   ├── provider_pool.py     # Provider 内 instance 选择
│   └── circuit_breaker.py   # 支持 instance 级别
│
├── providers/
│   ├── base.py              # Provider 基类
│   ├── registry.py          # Provider + Instance 注册
│   └── exa.py               # Exa Provider 实现
│
└── models/
    ├── config.py            # 新配置模型
    └── pool.py              # Pool 相关模型
```

## 关键类设计

```python
@dataclass
class ProviderConfig:
    """Provider 级别配置（通用）"""
    type: str
    enabled: bool
    capabilities: list[str]
    base_url: str
    timeout: int
    selection: SelectionConfig
    circuit_breaker: CircuitBreakerConfig

@dataclass
class InstanceConfig:
    """Instance 级别配置（差异化）"""
    provider: str           # 关联的 provider type
    api_key: str
    priority: int
    enabled: bool
    labels: list[str]

@dataclass
class SelectionConfig:
    """Instance 选择策略"""
    strategy: Literal["random", "round_robin", "priority"]
    retry_on_empty: bool
    max_retries_per_instance: int = 1

class ProviderPool:
    """
    管理同一个 Provider 的多个 Instances
    """
    def __init__(self, provider_config: ProviderConfig, instances: list[Instance]):
        self.config = provider_config
        self.instances = instances
        self.breakers: dict[str, CircuitBreaker] = {}
        self._rr_index = 0
    
    def select(self) -> Instance | None:
        """根据策略选择一个可用 instance"""
        available = self._get_available()
        if not available:
            return None
        
        strategy = self.config.selection.strategy
        if strategy == "random":
            return random.choice(available)
        elif strategy == "round_robin":
            return self._round_robin(available)
        elif strategy == "priority":
            return min(available, key=lambda x: x.config.priority)
```

## 优势

1. **配置清晰**：通用配置和差异化配置分离
2. **策略灵活**：每个 Provider 可以有自己的 instance 选择策略
3. **扩展性好**：新增 instance 只需添加配置，无需修改 provider 代码
4. **向后兼容**：可以自动从 v3.0 配置迁移
5. **符合直觉**：Provider = 类别，Instance = 具体账号

## 待讨论

1. **Circuit Breaker 级别**：
   - Option A: Instance 级别（每个 key 独立熔断）
   - Option B: Provider 级别（整个 provider 熔断）
   - Option C: 两者都有

2. **Metrics 聚合**：
   - 按 instance 统计？
   - 按 provider 聚合统计？
   - 两者都要？

3. **Web UI 展示**：
   - Provider 视图（类别）
   - Instance 视图（具体 key）
   - 两者都要？
