# Search Gateway 路线图

## 当前版本：v3.0

### 已完成功能 ✅

- [x] 多 provider 支持（8 个搜索引擎）
- [x] Circuit Breaker 熔断机制
- [x] 自动故障转移（Failover）
- [x] Round Robin 负载均衡
- [x] 多实例支持（同一 provider 多个 key）
- [x] HTTP API / MCP / CLI / SDK 多接口
- [x] 搜索历史记录
- [x] Web UI 配置管理
- [x] 运行时配置重载

---

## v3.1 - 指定 Provider + Failover

**目标：支持指定 provider 后仍继续 failover**

### P0：核心功能

- [ ] 修改 `_candidates()` 支持指定 provider 插入队首
- [ ] 修改 `execute()` 记录完整尝试历史
- [ ] 更新响应模型包含 `meta.attempted`
- [ ] 空结果检测与 failover 配置
- [ ] 更新所有接口返回尝试历史

### P1：观测性

- [ ] CLI `sg search -v` 显示详细尝试过程
- [ ] Web UI 显示最近搜索的 provider 链路
- [ ] Metrics 添加 failover 次数统计

### P2：文档

- [ ] 更新 API 文档
- [ ] 添加用户指南
- [ ] 更新 MCP 工具描述

---

## v3.2 - 内容增强 Providers

**目标：添加 AI 响应和内容增强能力**

### P0：新 Providers

- [ ] Perplexity AI（AI 响应）
- [ ] Kagi FastGPT（快速 AI 回答）
- [ ] Exa Answer（AI 问答）

### P1：Firecrawl 增强

- [ ] Firecrawl Crawl（深度爬取）
- [ ] Firecrawl Map（站点地图）
- [ ] Firecrawl Actions（页面交互）

### P2：内容增强

- [ ] Jina Grounding（事实验证）
- [ ] Kagi Enrichment（内容补充）

---

## v3.3 - GitHub 搜索

**目标：添加代码搜索能力**

### P0：GitHub Provider

- [ ] GitHub Code Search
- [ ] GitHub Repository Search
- [ ] GitHub User Search

### P1：代码搜索优化

- [ ] 代码结果格式化
- [ ] 语法高亮
- [ ] 结果缓存

---

## v3.4 - Pool & Intent

**目标：引入 Pool 概念，支持 Intent 路由**

### P0：Pool 管理

- [ ] Pool 配置与注册
- [ ] Pool 级别的 failover 策略
- [ ] Intent 到 Pool 的映射

### P1：Intent 系统

- [ ] 预定义 Intents（general, factual, research, cheap）
- [ ] Intent 自动识别（可选）
- [ ] Intent 路由规则

### P2：高级路由

- [ ] Tag -based 路由
- [ ] 自定义路由规则
- [ ] A/B 测试支持

---

## v3.5 - 结果优化

**目标：提升搜索结果质量**

### P0：结果处理

- [ ] 多 provider 结果合并
- [ ] 结果去重
- [ ] 结果排序优化

### P1：智能功能

- [ ] 结果摘要生成
- [ ] 相关搜索建议
- [ ] 搜索历史推荐

### P2：个性化

- [ ] 用户偏好学习
- [ ] 领域定制
- [ ] 个性化排序

---

## Backlog（待定）

### 可能的方向

- [ ] 搜索结果缓存层
- [ ] 分布式部署支持
- [ ] 更细粒度的配额管理
- [ ] 成本追踪与限制
- [ ] 多用户支持
- [ ] 搜索分析仪表盘
- [ ] 插件系统

### 明确不做

- 智能推荐 provider（基于内容类型）
- 复杂结果质量评分
- 商业化计费系统
- 大规模 research 编排（如 Deep Research）
- 多租户隔离

---

## 版本发布计划

| 版本 | 预计时间 | 核心主题 |
|-----|---------|---------|
| v3.1 | 2025 Q2 | 指定 Provider + Failover |
| v3.2 | 2025 Q2 | AI 响应 + 内容增强 |
| v3.3 | 2025 Q3 | GitHub 搜索 |
| v3.4 | 2025 Q3 | Pool & Intent |
| v3.5 | 2025 Q4 | 结果优化 |

---

## 决策记录

### 2025-03: 指定 Provider 后是否 Failover？

**决策**：指定 provider 后仍继续 failover

**理由**：
1. 搜索的本质是获取内容，不是选择 provider
2. 用户指定 provider 是表达偏好，不是锁定
3. 高可用是产品的核心承诺

**实现**：
- 指定 provider 插入候选列表队首
- 失败/空结果后继续尝试其他 provider
- 返回结果包含实际使用的 provider 和尝试历史

---

## 贡献指南

想参与开发？建议从这些任务开始：

1. **Good First Issue**
   - 添加新的 provider 支持
   - 改进错误信息
   - 添加更多测试

2. **Help Wanted**
   - 新 provider 适配
   - 文档翻译
   - 性能优化

3. **Core Development**
   - 需要讨论设计方案
   - 联系维护者
