# Search Gateway v4.0 配置与路由实现文档

## 设计结论

> **配置：Provider Group + Instance List + Runtime State 分离**  
> **路由：先选 Provider，再在 Provider 内随机选 Instance**

---

## 1. 配置模型

### 1.1 文件结构

```
config/
├── config.json           # 主配置（结构、分组、策略）
├── config.secrets.json   # 密钥（可选，gitignored）
└── runtime-state.json    # 运行时状态（自动维护）
```

### 1.2 主配置 (config.json)

```json
{
  "version": "4.0",
  "providers": {
    "exa": {
      "enabled": true,
      "priority": 10,
      "selection": "random",
      "is_fallback": false,
      "tags": ["research", "semantic"],
      "defaults": {
        "timeout": 30000,
        "url": "https://api.exa.ai",
        "capabilities": ["search", "extract"]
      },
      "instances": [
        {
          "id": "exa-prod",
          "enabled": true,
          "api_key": "${EXA_API_KEY_1}",
          "priority": 1
        },
        {
          "id": "exa-backup",
          "enabled": true,
          "api_key": "${EXA_API_KEY_2}",
          "priority": 2
        }
      ]
    },
    "tavily": {
      "enabled": true,
      "priority": 20,
      "selection": "random",
      "tags": ["general", "llm-friendly"],
      "defaults": {
        "timeout": 30000,
        "capabilities": ["search", "extract", "research"]
      },
      "instances": [
        {"id": "tavily-1", "enabled": true, "api_key": "${TAVILY_API_KEY_1}"},
        {"id": "tavily-2", "enabled": true, "api_key": "${TAVILY_API_KEY_2}"}
      ]
    },
    "duckduckgo": {
      "enabled": true,
      "priority": 100,
      "selection": "random",
      "is_fallback": true,
      "tags": ["free", "privacy"],
      "defaults": {
        "timeout": 30000,
        "capabilities": ["search"]
      },
      "instances": [
        {"id": "duckduckgo"}
      ]
    }
  },
  "execution": {
    "default_strategy": "priority",
    "failover": {
      "max_providers": 3,
      "empty_result_failover": true
    }
  }
}
```

### 1.3 密钥配置 (config.secrets.json)

```json
{
  "exa-prod": {"api_key": "exa-key-1"},
  "exa-backup": {"api_key": "exa-key-2"},
  "tavily-1": {"api_key": "tvly-key-1"},
  "tavily-2": {"api_key": "tvly-key-2"}
}
```

或环境变量：
```bash
export EXA_API_KEY_1="exa-key-1"
export EXA_API_KEY_2="exa-key-2"
export TAVILY_API_KEY_1="tvly-key-1"
export TAVILY_API_KEY_2="tvly-key-2"
```

### 1.4 运行时状态 (runtime-state.json)

```json
{
  "instances": {
    "exa-prod": {
      "disabled_until": "2025-03-24T10:00:00Z",
      "last_failure_type": "quota",
      "request_count": 150,
      "success_count": 147
    },
    "exa-backup": {
      "disabled_until": null,
      "last_failure_type": null,
      "request_count": 50,
      "success_count": 50
    }
  }
}
```

---

## 2. Python 模型

```python
# src/sg/models/config_v4.py

from pydantic import BaseModel, Field
from typing import Literal

class ProviderInstanceConfig(BaseModel):
    """Provider 实例配置（差异化）"""
    id: str
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    timeout: int | None = None
    priority: int = 10
    env: dict[str, str] = {}

class ProviderDefaults(BaseModel):
    """Provider 默认配置"""
    timeout: int = 30000
    url: str | None = None
    capabilities: list[str] = ["search"]

class ProviderGroupConfig(BaseModel):
    """Provider 组配置"""
    enabled: bool = True
    priority: int = 10
    selection: Literal["random", "round_robin", "priority"] = "random"
    is_fallback: bool = False
    tags: list[str] = []
    defaults: ProviderDefaults = ProviderDefaults()
    instances: list[ProviderInstanceConfig]

class ExecutionConfig(BaseModel):
    """执行配置"""
    default_strategy: Literal["priority", "round_robin", "random"] = "priority"
    failover: FailoverConfig = FailoverConfig()

class GatewayConfigV4(BaseModel):
    """v4.0 主配置"""
    version: str = "4.0"
    providers: dict[str, ProviderGroupConfig]
    execution: ExecutionConfig = ExecutionConfig()

class InstanceRuntimeState(BaseModel):
    """实例运行时状态"""
    disabled_until: str | None = None
    last_failure_type: str | None = None
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0

class RuntimeState(BaseModel):
    """运行时状态（自动维护）"""
    instances: dict[str, InstanceRuntimeState] = {}
```

---

## 3. 运行时架构

### 3.1 核心类

```python
# src/sg/core/provider_pool.py

class ProviderPool:
    """
    管理同一个 Provider 的多个 Instances
    负责：Instance 选择、熔断管理、状态跟踪
    """
    
    def __init__(self, 
                 name: str,
                 config: ProviderGroupConfig,
                 runtime_states: dict[str, InstanceRuntimeState]):
        self.name = name
        self.config = config
        self.runtime_states = runtime_states
        self._rr_index = 0
    
    def select_instance(self, exclude: set[str] | None = None) -> ProviderInstance | None:
        """
        选择一个可用 instance
        
        逻辑：
        1. 过滤：enabled + 未熔断 + 不在 exclude 中
        2. 按 selection 策略选择
        """
        available = [
            inst for inst in self.config.instances
            if inst.enabled 
            and not self._is_disabled(inst.id)
            and (exclude is None or inst.id not in exclude)
        ]
        
        if not available:
            return None
        
        strategy = self.config.selection
        if strategy == "random":
            return random.choice(available)
        elif strategy == "round_robin":
            idx = self._rr_index % len(available)
            self._rr_index += 1
            return available[idx]
        elif strategy == "priority":
            return min(available, key=lambda x: x.priority)
    
    def _is_disabled(self, instance_id: str) -> bool:
        """检查 instance 是否被禁用"""
        state = self.runtime_states.get(instance_id)
        if not state or not state.disabled_until:
            return False
        return datetime.now() < datetime.fromisoformat(state.disabled_until)
    
    def has_available_instance(self) -> bool:
        """检查是否还有可用 instance"""
        return self.select_instance() is not None
    
    def record_success(self, instance_id: str):
        """记录成功"""
        state = self.runtime_states.setdefault(instance_id, InstanceRuntimeState())
        state.request_count += 1
        state.success_count += 1
        # 恢复逻辑...
    
    def record_failure(self, instance_id: str, failure_type: str):
        """记录失败，可能触发禁用"""
        state = self.runtime_states.setdefault(instance_id, InstanceRuntimeState())
        state.request_count += 1
        state.failure_count += 1
        state.last_failure_type = failure_type
        
        # 触发禁用
        if self._should_disable(instance_id):
            state.disabled_until = self._calculate_disabled_until(failure_type)
```

```python
# src/sg/core/executor_v4.py

class ExecutorV4:
    """
    v4.0 执行器
    两层路由：Provider → Instance
    """
    
    def __init__(self, 
                 execution_config: ExecutionConfig,
                 provider_pools: dict[str, ProviderPool],
                 fallback_pool: ProviderPool | None):
        self.config = execution_config
        self.pools = provider_pools
        self.fallback = fallback_pool
    
    async def execute(self, 
                      capability: str,
                      operation: Callable,
                      provider: str | None = None) -> ExecutionResult:
        """
        执行操作
        
        路由逻辑：
        1. 如果指定 provider：
           - 先在该 provider pool 中选择 instance 尝试
           - 如果该 pool 所有 instances 都失败，继续其他 pools
        
        2. 如果未指定 provider：
           - 按 priority 排序选择 capable pools
           - 在每个 pool 内选择 instance 尝试
           - 失败则 failover 到下一个 pool
        """
        attempted = []
        
        # 获取候选 pools
        if provider:
            # 指定 provider 优先
            if provider in self.pools:
                candidate_pools = [self.pools[provider]] + [
                    p for name, p in self.pools.items() 
                    if name != provider and p.has_capability(capability)
                ]
            else:
                candidate_pools = self._get_capable_pools(capability)
        else:
            candidate_pools = self._get_capable_pools(capability)
        
        # 尝试每个 pool
        for pool in candidate_pools[:self.config.failover.max_providers]:
            result = await self._try_pool(pool, operation, attempted)
            if result.success:
                return ExecutionResult(
                    data=result.data,
                    provider=pool.name,
                    instance=result.instance_id,
                    attempted=attempted
                )
        
        # 尝试 fallback
        if self.fallback and self.fallback.has_capability(capability):
            result = await self._try_pool(self.fallback, operation, attempted)
            if result.success:
                return ExecutionResult(
                    data=result.data,
                    provider=self.fallback.name,
                    instance=result.instance_id,
                    attempted=attempted
                )
        
        # 全部失败
        raise AllProvidersFailedError(attempted)
    
    async def _try_pool(self, 
                        pool: ProviderPool, 
                        operation: Callable,
                        attempted: list) -> TryResult:
        """尝试一个 pool 内的 instance"""
        tried_in_pool = set()
        
        while True:
            instance = pool.select_instance(exclude=tried_in_pool)
            if not instance:
                break  # pool 内无可用 instance
            
            tried_in_pool.add(instance.id)
            
            try:
                start = time.perf_counter()
                result = await operation(instance)
                latency = (time.perf_counter() - start) * 1000
                
                # 检查空结果
                if self._is_empty(result) and self.config.failover.empty_result_failover:
                    attempted.append(AttemptInfo(
                        provider=pool.name,
                        instance=instance.id,
                        status="empty",
                        latency_ms=latency
                    ))
                    continue
                
                # 成功
                pool.record_success(instance.id)
                attempted.append(AttemptInfo(
                    provider=pool.name,
                    instance=instance.id,
                    status="success",
                    latency_ms=latency
                ))
                return TryResult(success=True, data=result, instance_id=instance.id)
                
            except Exception as e:
                failure_type = classify_error(e)
                pool.record_failure(instance.id, failure_type)
                attempted.append(AttemptInfo(
                    provider=pool.name,
                    instance=instance.id,
                    status="failed",
                    error=failure_type,
                    latency_ms=(time.perf_counter() - start) * 1000
                ))
                # 继续尝试 pool 内其他 instance
                continue
        
        return TryResult(success=False)
    
    def _get_capable_pools(self, capability: str) -> list[ProviderPool]:
        """获取支持该 capability 的 pools，按 priority 排序"""
        capable = [
            pool for pool in self.pools.values()
            if pool.has_capability(capability) and pool.has_available_instance()
        ]
        return sorted(capable, key=lambda p: p.config.priority)
```

---

## 4. 迁移实现

```python
# src/sg/models/config_migration.py

def migrate_v3_to_v4(v3_config: dict) -> GatewayConfigV4:
    """
    v3 → v4 自动迁移
    
    规则：
    1. 按 type 分组
    2. 公共字段 → provider.defaults
    3. 差异字段 → instance
    4. priority 取最小值作为 provider priority
    """
    if v3_config.get("version") == "4.0":
        return GatewayConfigV4.model_validate(v3_config)
    
    # 按 type 分组
    by_type: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for name, cfg in v3_config.get("providers", {}).items():
        ptype = cfg.get("type", name)
        by_type[ptype].append((name, cfg))
    
    v4_providers = {}
    
    for ptype, instances in by_type.items():
        # 提取公共配置（取第一个实例的）
        first_name, first_cfg = instances[0]
        
        # 计算 provider 级 priority（取最小）
        min_priority = min(
            cfg.get("priority", 10) 
            for _, cfg in instances
        )
        
        provider_cfg = ProviderGroupConfig(
            enabled=first_cfg.get("enabled", True),
            priority=min_priority,
            selection="random",  # v4 默认 random
            is_fallback=first_cfg.get("is_fallback", False),
            defaults=ProviderDefaults(
                timeout=first_cfg.get("timeout", 30000),
                url=first_cfg.get("url"),
                capabilities=infer_capabilities(ptype)
            ),
            instances=[
                ProviderInstanceConfig(
                    id=name,
                    enabled=cfg.get("enabled", True),
                    api_key=cfg.get("api_key"),
                    url=cfg.get("url"),
                    timeout=cfg.get("timeout"),
                    priority=cfg.get("priority", 10)
                )
                for name, cfg in instances
            ]
        )
        
        v4_providers[ptype] = provider_cfg
    
    return GatewayConfigV4(
        version="4.0",
        providers=v4_providers,
        execution=ExecutionConfig(
            default_strategy="priority",
            failover=FailoverConfig(
                max_attempts=v3_config.get("executor", {})
                    .get("failover", {})
                    .get("max_attempts", 3),
                empty_result_failover=True
            )
        )
    )
```

---

## 5. 初始化流程

```python
# src/sg/server/gateway_v4.py

class GatewayV4:
    def __init__(self, config_path: str = "config.json"):
        # 1. 加载主配置
        self.config = self._load_config(config_path)
        
        # 2. 加载密钥（合并到 instances）
        self._load_secrets()
        
        # 3. 加载运行时状态
        self.runtime_state = self._load_runtime_state()
        
        # 4. 初始化 Provider Pools
        self.pools = self._init_pools()
        
        # 5. 初始化 Executor
        self.executor = ExecutorV4(
            execution_config=self.config.execution,
            provider_pools=self.pools,
            fallback_pool=self._get_fallback_pool()
        )
    
    def _load_config(self, path: str) -> GatewayConfigV4:
        """加载配置，自动迁移 v3"""
        with open(path) as f:
            data = json.load(f)
        
        if data.get("version") != "4.0":
            logger.info(f"Migrating config from {data.get('version', 'unknown')} to 4.0")
            config = migrate_v3_to_v4(data)
            # 备份原配置
            backup_path = f"{path}.v3.backup"
            shutil.copy(path, backup_path)
            # 保存迁移后的配置
            with open(path, 'w') as f:
                json.dump(config.model_dump(), f, indent=2)
            return config
        
        return GatewayConfigV4.model_validate(data)
    
    def _init_pools(self) -> dict[str, ProviderPool]:
        """初始化 Provider Pools"""
        pools = {}
        for name, provider_cfg in self.config.providers.items():
            if not provider_cfg.enabled:
                continue
            
            # 获取该 provider 下所有 instance 的运行时状态
            instance_states = {
                inst.id: self.runtime_state.instances.get(inst.id, InstanceRuntimeState())
                for inst in provider_cfg.instances
            }
            
            pools[name] = ProviderPool(
                name=name,
                config=provider_cfg,
                runtime_states=instance_states
            )
        
        return pools
```

---

## 6. 关键行为验证

### 场景 1：Exa 多 Key 随机选择

```
Config:
  exa:
    selection: random
    instances: [exa-prod, exa-backup]

Request: search("AI")

Execution:
1. Executor 选择 Provider "exa" (priority=10)
2. ProviderPool "exa" 随机选择 instance
   - 50% 概率选 exa-prod
   - 50% 概率选 exa-backup
3. 使用选中的 instance 执行
4. 记录成功/失败到 runtime-state
```

### 场景 2：Exa 一个 Key 被禁用

```
Runtime State:
  exa-prod: disabled_until=2025-03-24T10:00:00Z
  exa-backup: disabled_until=null

Request: search("AI")

Execution:
1. ProviderPool "exa" 过滤 disabled instances
2. 只有 exa-backup 可用
3. 选择 exa-backup 执行
4. Provider "exa" 整体仍可用
```

### 场景 3：Exa 所有 Key 被禁用

```
Runtime State:
  exa-prod: disabled
  exa-backup: disabled

Request: search("AI")

Execution:
1. ProviderPool "exa" 无可用 instance
2. Provider "exa" 标记为不可用
3. Failover 到下一个 Provider (tavily)
4. 尝试 Tavily Pool 内的 instances
```

### 场景 4：指定 Provider 但 Failover

```
Request: search("AI", provider="exa")

Execution:
1. 优先尝试 Provider "exa"
2. Exa 所有 instances 失败/禁用
3. 继续尝试其他 Providers (tavily, brave, duckduckgo)
4. 返回实际成功的 Provider + Instance
```

---

## 7. 实现 checklist

### Phase 1: 模型与配置
- [ ] `config_v4.py` 新配置模型
- [ ] `config_migration.py` v3→v4 迁移
- [ ] `runtime_state.py` 运行时状态管理

### Phase 2: 核心逻辑
- [ ] `provider_pool.py` Provider Pool 实现
- [ ] `executor_v4.py` 两层路由执行器
- [ ] 熔断/禁用逻辑（instance 级别）

### Phase 3: 集成
- [ ] `gateway_v4.py` 新 Gateway 初始化
- [ ] HTTP API 更新
- [ ] MCP Server 更新
- [ ] CLI 更新

### Phase 4: 观测性
- [ ] 尝试历史返回
- [ ] Metrics 更新
- [ ] Web UI 更新

### Phase 5: 测试
- [ ] 单元测试
- [ ] 集成测试
- [ ] 迁移测试

---

## 8. 一句话总结

> **v4.0 把扁平的实例列表升级为分层的 Provider Group + Instance Pool，让路由更符合"先选类别，再选入口"的真实语义，同时保持配置的简洁和灵活。**
