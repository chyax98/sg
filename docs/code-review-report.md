# 代码和配置 Review 报告

## 审查范围

- Web UI 配置合理性
- History 机制合理性
- 代码质量和一致性
- 配置文件结构
- 文档完整性

---

## 发现的问题

### 1. Web UI 配置问题

**当前状态**：
- `web_ui.enabled` 配置项存在但功能不明确
- Web UI 实际上是 HTTP 服务器的一部分，无法单独禁用
- 配置项容易误导用户

**建议**：
- 移除 `web_ui.enabled` 配置项（Web UI 是 HTTP 服务器的一部分）
- 或者明确说明这个配置项的实际作用

### 2. History 配置问题

**当前状态**：
- `history.dir` 默认 `~/.sg/history`
- `history.max_entries` 配置项存在但未实现
- 历史记录强制开启，但配置项仍然存在

**建议**：
- 移除 `history.max_entries`（未实现的功能）
- 简化 History 配置，只保留 `dir`

### 3. 配置文件冗余

**当前状态**：
- `config.json` 包含很多默认值
- 用户配置文件过于冗长

**建议**：
- `sg init` 生成的配置应该更简洁
- 只包含必要的配置项，其他使用默认值

### 4. Provider 配置复杂度

**当前状态**：
- 每个 provider 都需要配置 `type`, `enabled`, `priority`, `selection`, `defaults`, `instances`
- 对于简单场景过于复杂

**建议**：
- 提供更简洁的配置方式
- 大部分字段应该有合理的默认值

### 5. 代码质量问题

**Ruff 检测到的问题**：
- B904: 异常链缺失（5 处）
- W293: 空行包含空格（1 处）

**建议**：
- 修复这些 linting 问题

### 6. 文档问题

**当前状态**：
- 文档分散在多个文件中
- 部分文档内容重复
- 缺少快速开始指南

**建议**：
- 在 README 中添加 Quick Start
- 整合重复内容

---

## 优先级

### P0（必须修复）
1. 修复 ruff 检测到的代码质量问题
2. 简化 `sg init` 生成的配置模板
3. 移除未实现的 `history.max_entries` 配置

### P1（重要优化）
4. 澄清或移除 `web_ui.enabled` 配置
5. 优化 Provider 配置的默认值
6. 在 README 添加 Quick Start

### P2（可选改进）
7. 整合重复的文档内容
8. 添加配置验证和错误提示

---

## 建议的配置模板（简化版）

```json
{
  "server": {
    "port": 8100
  },
  "providers": {
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "fallback_for": ["search"]
    }
  }
}
```

大部分配置使用默认值，用户只需要配置必要的部分。

---

## 下一步行动

1. 修复代码质量问题（B904, W293）
2. 简化配置模板
3. 更新文档
4. 提交变更
5. 合并到 main 分支
