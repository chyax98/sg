# Search Gateway 产品蓝图

## 一句话定位

面向个人用户的高可用搜索入口。

用户看到的是一个稳定的搜索 API / MCP tool / CLI 搜索命令；系统内部通过多 provider、多实例、quota 感知禁用与自动切换，解决搜索额度分散、单 key 不稳定、免费额度脆弱的问题。

## 核心目标

这个产品最终要解决的不是"如何管理一堆 API Key"，而是：

1. **尽可能始终返回结果** —— 这是第一优先级
2. **在免费额度有限的前提下尽可能延长整体可用时间**
3. **让用户几乎不需要关心底层 provider 的运行状态**

`池化` 是手段，不是终极目的。  
`高可用搜索能力` 才是产品交付物。

## 当前已实现策略

当前产品已经落地的是一套偏保守的高可用策略，不做智能 provider 决策：

1. 外层按 provider group 调度
2. 内层按 group 内 instances 调度
3. 实例失败时先切同组其他实例
4. 同组不可用后再切下一个 group
5. 全部常规 group 失败后再走 fallback

默认配置的含义是：

- 外层 `round_robin`
  - 在不同 provider 类型之间分散请求
- 内层 `random`
  - 在同类 provider 的多个账号之间随机分摊
- breaker 按实例生效
  - 某个 key 坏了，不会拖死整个 provider 类别
- quota / auth / transient 分开处理
  - 配额、认证、临时错误采用不同禁用时长

当前明确不做：

- 智能推荐哪个 provider 最优
- 基于结果质量自动改换 provider
- 把空结果自动判定为失败并继续切换

## 目标用户

单人使用者，典型特征：

- 手里有多个搜索 provider 的免费 key 或少量试用账号
- 不希望频繁切换 provider，也不想维护复杂工作流
- 更在意"这次能不能搜到"和"连续几天是否稳定可用"
- 不太关心内部管理细节，但希望出问题时能排查

## 用户真正关心的事

用户通常不 care：

- key 是如何轮询的
- breaker 何时打开
- quota 是按日还是按月恢复
- provider 内部优先级如何配置

用户真正 care 的只有这些结果：

1. 搜索是否高可用
2. 是否尽量不空结果
3. 是否尽量快
4. 是否在连续使用中不突然失效

因此，管理面应该存在，但必须退居二线。

## 产品承诺

对用户的承诺应该非常简单：

- 一个统一搜索入口
- 自动在可用资源之间切换
- 尽量不因单个 key 失效而中断
- 尽量少维护
- 出问题时可解释、可排查

## 核心设计原则：内容优先

> **搜索的本质是获取内容，而不是选择 provider。**

这意味着：

1. **指定 provider 不是承诺，而是偏好**
   - 用户可以指定一个 provider group 作为起点
   - 如果指定的是 group，系统仍会在该 group 内切换实例
   - 如果指定的是 instance，系统会先尝试该 instance，再走 fallback
   - 最终目标是返回内容，而不是满足某个固定入口

2. **Failover 是默认行为**
   - 不指定 provider 时，系统会按全局策略在多个 group 间切换
   - 指定 group 时，系统会在该 group 内切换实例
   - 所有正常路径失败后，系统会继续尝试 fallback

## 产品形态

### 前台形态

用户感知到的是：

- HTTP API
- Python SDK
- MCP tools
- CLI

它们都应表现为同一个稳定搜索服务，而不是一堆 provider 的控制台。

### 后台形态

内部支撑能力包括：

- 多 provider 多实例池化
- round-robin / failover 路由
- quota / auth / transient 分类处理
- 熔断、恢复、禁用时间管理
- 指定 group / instance 时的受限执行语义
- 基础状态页与实例级计数

## 产品对象模型

下面这部分是产品设计方向，不等于当前所有能力都已实现。

### 1. Instance

一个具体的 provider 实例，对应一个账号、一个 key，或一个自建入口。

示例：

- `brave-1`
- `brave-2`
- `tavily-main`
- `searxng-home`

### 2. Pool

一组 instance 的组合，是用户真正应该面向的主要对象。

Pool 负责表达"这组资源要承担什么用途"，而不是让用户直接思考所有 provider。

示例：

- `default`
- `fast_search`
- `factual`
- `research`
- `fallback_free`

### 3. Policy

Pool 的行为规则：

- 轮询还是 failover
- 最大尝试次数
- quota 如何禁用
- auth 错误如何处理
- 空结果是否继续尝试
- 指定 provider 后是否继续跨 group failover

### 4. Intent

调用方的搜索意图。Intent 不是黑箱智能，而是显式表达用途。

示例：

- `general`
- `factual`
- `research`
- `cheap`
- `fallback_only`

Intent 最终映射到某个 pool 或某组 policy。

## 关键行为定义

### 搜索行为

```
用户调用: search(query, provider="tavily")

执行链路:
1. 只在 Tavily group 内选择一个健康 instance
2. 当前 instance 失败 → 尝试 Tavily group 内其他 instance
3. Tavily group 无可用 instance → 尝试 fallback group
4. fallback 失败 → 返回错误

返回结果包含:
- 实际使用的 provider
- 基础运行状态信息
```

### 熔断与恢复

```
provider 连续失败 3 次 → 熔断 (OPEN)
熔断后等待退避时间 → 半开 (HALF_OPEN)
半开状态成功 2 次 → 恢复 (CLOSED)
```

## 设计原则

### 1. 高可用优先于智能

产品的第一优先级不是"自动选最优 provider"，而是"尽量别失败"。

### 2. 内容优先于 Provider

用户要的是搜索结果，不是某个特定 provider 的响应。当前实现里，指定 group 是偏好，指定 instance 更接近 pin。

### 3. 可解释优先于黑箱

系统可以自动切换，但必须尽量让用户知道：

- 为什么跳过某个 provider
- 为什么落到 fallback
- 为什么当前某个实例不可用
- **最终结果是来自哪个 provider**

### 4. 默认无感，出问题时可排查

日常使用中，用户不该被管理细节打扰。  
只有在失败、额度耗尽或配置异常时，才暴露状态和控制面。

### 5. 管理面最小化，但必须存在

状态页、实例列表、禁用原因、简单计数是必要的。  
复杂运营控制台、成本系统、智能推荐系统不是当前重点。

### 6. Pool 是前台对象，Provider 是后台资源

产品逐步应从"provider 列表驱动"转向"pool 驱动"。

## P0 范围

必须优先做对的能力：

1. ✅ 统一搜索接口
2. ✅ 多实例轮询与自动 failover
3. ✅ quota / auth / transient 分类禁用
4. ✅ 指定 group / instance 的执行语义
5. ✅ 单一 fallback 组
6. ✅ provider group + instance 配置模型
7. ✅ 基础状态查看
8. ✅ 实例级请求计数
9. ✅ 最小可用的配置和热重载

## P1 范围

在 P0 稳定后继续完善：

1. Pool 概念成为一等公民
2. Intent / tag 路由
3. provider 能力矩阵与参数支持声明
4. quota reset 策略模型
5. 更直观的可用性视图
6. 空结果继续尝试策略
7. 搜索结果合并与去重
8. 多 provider 结果聚合

## P2 范围

体验增强能力：

1. 更好的 Web UI
2. MCP 状态与资源查询工具
3. 更细粒度的可视化配置
4. 历史结果复用或轻量缓存

## 当前不应优先做的事

这些方向会把产品重心带偏：

- 智能推荐 provider
- 复杂结果质量评分
- 成本优化体系
- 大规模 research 编排
- 复杂商业化控制台

## 北极星指标

最适合作为产品的核心指标不是管理指标，而是结果指标：

1. **搜索请求成功率** —— 最终拿到结果的比例
2. **非空结果率** —— 有实质内容的比例
3. **平均搜索延迟** —— 首次成功返回的时间
4. **单实例故障对整体成功率的影响** —— 容错能力
5. **用户主动干预次数** —— 系统自治程度

如果这些指标在提升，说明产品正在真正解决"搜索额度分散"带来的体验问题。

## 一句话蓝图

把零散、脆弱、额度有限的个人搜索资源，编排成一个稳定、透明、低维护的高可用搜索能力。

> **尽量少让用户关心 provider，尽量稳定地把结果送回来。**
