# 更新日志

本项目的所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 新增

- **Daemon 模式**：`sg start -d` 后台启动网关，自动写日志到 `~/.sg/logs/gateway.log`，启动后验证健康状态
- **CLI `-h` 支持**：所有命令支持 `-h` 作为 `--help` 的简写

### 变更

- **破坏性变更**：移除 MCP SSE 模式，仅保留 stdio 模式。原因：FastMCP 3.1.1 的 SSE 实现存在 bug，客户端在初始化完成前发送请求导致 `Received request before initialization was complete` 错误。stdio 模式更稳定可靠

## [1.0.0] - 2026-03-24

首个正式版本发布！🎉

### 核心特性

- **8 种搜索 Provider**：Tavily, Exa, Brave, You.com, Firecrawl, Jina, SearXNG, DuckDuckGo
- **Provider Group + Instance Pool**：同一 provider 类型下可配置多个实例
- **Circuit Breaker**：三态熔断器自动熔断与恢复
- **两层路由**：Provider Group 选择 + Instance 选择
- **多接口**：HTTP REST API + MCP 协议（stdio + SSE）+ CLI + Python SDK
- **搜索历史**：文件系统异步存储，支持查询回溯

### MCP 集成

- **SSE 模式**：持续运行的 gateway，多客户端共享
- **stdio 模式**：临时使用，每次连接启动新实例
- 支持 Claude Desktop 和 Claude Code

### 开发工具

- Makefile 快速开发命令
- 开发模式安装（代码修改自动生效）
- 完整的测试套件（116 个测试）

### 代码质量

- 添加 mypy 类型检查和 ruff linting 配置
- CLI 输出优化：简化格式以减少 token 使用
- 配置模板简化：降低初次使用门槛
- 解决 ruff linting 检查发现的代码规范问题

## 2026-03-23

### 新增

- **批量搜索支持**：通过 `/search/batch` 端点和 `sg search q1 q2 q3` CLI 命令并行执行多个查询
- **基于文件的结果存储**：所有搜索结果保存到 `~/.sg/history/`，返回文件元数据（大小、行数、字数）供 AI 智能读取
- **SearXNG Provider**：支持自建 SearXNG 实例作为搜索源
- **全局 CLI 安装**：支持 `uv tool install` 全局安装
- **自动启动服务**：CLI 命令检测网关未运行时自动后台启动
- **完整日志链路**：添加 DEBUG 级别日志，覆盖执行全流程（候选列表、实例选择、熔断器状态变更）
- **测试手册**：`docs/testing.md` 提供可复用的黑盒测试用例

### 变更

- **破坏性变更**：搜索响应现在返回 `result_file` 路径而非完整结果。AI 工具必须读取文件才能访问内容
- **破坏性变更**：历史记录现在始终启用且无法禁用。`history.enabled` 配置选项已移除
- **破坏性变更**：Fallback 机制从全局改为能力特定。配置 `fallback_for: ["search"]` 而非 `is_fallback: true`
- **Provider 优先级修正**：Provider Group 使用绝对优先级，不受 Round Robin 策略影响。策略仅作用于 Instance 级别
- **CLI 搜索输出**：现在返回带元数据的文件路径，而非直接打印结果

### 修复

- Round Robin 负载均衡现在使用 `threading.Lock` 实现线程安全
- 移除所有对已弃用 `is_fallback` 字段的引用（替换为 `fallback_for`）
- 类型安全改进：解决 executor 和 provider 实现中的 mypy 错误
- Circuit Breaker 状态变更日志缺失问题

### 移除

- 移除旧配置格式兼容层（不再支持 v2.x 配置）
- 移除 `history.enabled` 配置项（历史记录强制开启）

### 迁移指南

**如果你使用 HTTP API 或 MCP 工具：**

- 搜索响应现在包含指向 JSON 文件的 `result_file` 字段
- 读取文件以访问完整搜索结果
- 文件元数据帮助决定读取策略（小文件直接读取，大文件使用 grep/jq）

**如果你有自定义配置：**

- 将 `is_fallback: true` 替换为 `fallback_for: ["search"]`
- 从配置中移除 `history.enabled`（历史记录始终开启）

**如果你使用 CLI：**

- `sg search` 现在输出文件路径而非结果
- 使用 `cat <path>` 或 `jq` 查看结果
- 多查询：`sg search "q1" "q2" "q3"` 并行运行
