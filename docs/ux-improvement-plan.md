# UX 改进规划

## 调研发现

### 1. 配置文件位置问题
**现状**：
- CLI 默认使用当前目录的 `config.json`
- 每个命令都有 `--config` 参数，默认值 `"config.json"`
- 没有全局配置路径

**问题**：
- 作为全局工具安装后，用户在任意目录执行 `sg` 命令会找不到配置
- 不符合全局工具的使用习惯

**改进方案**：
- 默认配置路径改为 `~/.sg/config.json`
- 优先级：`--config` 参数 > `~/.sg/config.json` > 当前目录 `config.json`（兼容）
- 首次运行时自动创建 `~/.sg/config.json` 模板

---

### 2. MCP 工具描述和参数
**现状**：
- `search()`: 描述简单，但参数说明清晰
- `extract()`: 描述简单
- `research()`: 描述简单
- `list_providers()`: 描述简单

**问题**：
- 工具描述不够详细，AI 可能不清楚何时使用
- 缺少使用场景说明
- 返回格式说明不够清晰

**改进方案**：
- 增强每个工具的 docstring，包含：
  - 详细功能说明
  - 使用场景
  - 返回格式说明
  - 示例用法
- `search()` 返回文件路径后，建议 AI 如何读取（小文件直接读，大文件用 jq/grep）

---

### 3. MCP 连接方式
**现状**：
- 支持 stdio 模式：`sg mcp`
- 支持 HTTP/SSE 模式：`run_http()` 方法存在但未暴露 CLI

**问题**：
- 用户不知道如何配置 Claude Code/Claude Desktop
- 缺少配置示例

**改进方案**：
- 文档中添加 Claude Desktop 配置示例
- 文档中添加 Claude Code (MCP) 配置示例
- 考虑添加 `sg mcp-config` 命令自动生成配置

---

### 4. CLI 返回结果引导
**现状**：
- `search` 返回文件路径 + 元数据（大小、行数、字数）
- 没有后续操作提示

**问题**：
- 用户不知道如何查看结果
- 对于大文件，用户可能直接 cat 导致输出过多

**改进方案**：
- 添加智能提示：
  - 小文件（<5KB）：提示 `cat <file>` 或 `jq . <file>`
  - 中文件（5-50KB）：提示 `jq '.results[] | {title, url}' <file>`
  - 大文件（>50KB）：提示 `jq '.results[0:5]' <file>` 或 `grep -i "keyword" <file>`

---

### 5. Onboarding 流程
**现状**：
- 安装后直接使用，没有引导
- 没有初始化命令
- 没有配置向导

**问题**：
- 新用户不知道如何配置 API Key
- 不知道有哪些 Provider 可用
- 不知道如何测试

**改进方案**：
- 添加 `sg init` 命令：
  - 创建 `~/.sg/config.json` 模板
  - 交互式配置 API Key（可选）
  - 显示可用 Provider 列表
  - 运行测试搜索验证配置
- 首次运行任何命令时，检测配置不存在则提示运行 `sg init`

---

### 6. 文档细致化
**现状**：
- README 有基本说明
- ARCHITECTURE 有架构说明
- 缺少详细的使用指南

**问题**：
- 缺少 MCP 集成详细步骤
- 缺少常见问题解答
- 缺少最佳实践

**改进方案**：
- 创建 `docs/user-guide.md`：
  - 安装和初始化
  - 配置 API Key
  - 基本使用
  - MCP 集成（Claude Desktop + Claude Code）
  - 常见问题
- 创建 `docs/mcp-integration.md`：
  - Claude Desktop 配置
  - Claude Code 配置
  - 工具使用示例
  - 最佳实践

---

## 实施优先级

### P0（必须）
1. 配置文件路径改为 `~/.sg/config.json`
2. 添加 `sg init` 命令
3. 增强 MCP 工具描述

### P1（重要）
4. CLI 返回结果添加智能提示
5. 创建 MCP 集成文档
6. 创建用户指南

### P2（可选）
7. 添加 `sg mcp-config` 命令生成配置
8. 添加配置验证命令

---

## 实施计划

1. 修改配置加载逻辑（config.py, cli.py, _utils.py）
2. 添加 `sg init` 命令
3. 增强 MCP 工具 docstring
4. 修改 CLI 输出，添加智能提示
5. 创建文档
6. 测试验证
7. 更新 CHANGELOG
