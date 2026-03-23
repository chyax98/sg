# 贡献指南

感谢你对 Search Gateway 的关注！我们欢迎各种形式的贡献。

## 如何贡献

### 报告 Bug

如果你发现了 bug，请创建一个 issue，包含：

- 清晰的标题和描述
- 复现步骤
- 预期行为和实际行为
- 环境信息（操作系统、Python 版本等）
- 相关日志或错误信息

### 提出新功能

如果你有新功能的想法：

1. 先创建一个 issue 讨论这个功能
2. 说明为什么需要这个功能
3. 描述你期望的行为
4. 等待维护者反馈后再开始实现

### 提交代码

1. **Fork 仓库**

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **开发**
   ```bash
   # 开发模式安装
   make dev

   # 或者
   uv tool install --editable .
   ```

4. **测试**
   ```bash
   # 运行测试
   make test

   # 或者
   pytest tests/ -v
   ```

5. **提交代码**
   ```bash
   git add <files>
   git commit -m "feat: add your feature"
   ```

   提交信息格式：
   - `feat:` 新功能
   - `fix:` Bug 修复
   - `docs:` 文档更新
   - `refactor:` 代码重构
   - `test:` 测试相关
   - `chore:` 构建/工具相关

6. **推送并创建 PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## 开发指南

### 项目结构

```
search-gateway/
├── src/sg/           # 源代码
│   ├── cli/          # CLI 命令
│   ├── models/       # 数据模型
│   ├── providers/    # Provider 实现
│   ├── server/       # HTTP/MCP 服务器
│   └── sdk/          # Python SDK
├── tests/            # 测试
├── docs/             # 文档
└── scripts/          # 开发脚本
```

### 代码规范

- 使用 Python 3.12+
- 遵循 PEP 8 代码风格
- 使用类型注解
- 添加必要的注释和文档字符串

### 添加新 Provider

1. 在 `src/sg/providers/` 创建新文件
2. 继承 `SearchProvider` 基类
3. 实现必要的方法：
   ```python
   from .base import ProviderInfo, SearchProvider

   class MyProvider(SearchProvider):
       info = ProviderInfo(
           type="my_provider",
           display_name="My Provider",
           capabilities=("search",),
       )

       async def initialize(self):
           # 初始化逻辑
           pass

       async def search(self, query: str, **kwargs):
           # 搜索实现
           pass
   ```
4. 在 `src/sg/providers/registry.py` 注册
5. 添加测试
6. 更新文档

### 运行测试

```bash
# 所有测试
pytest tests/ -v

# 特定测试
pytest tests/test_providers.py -v

# 带覆盖率
pytest tests/ --cov=src/sg --cov-report=html
```

### 文档

- 更新 README.md（如果影响用户使用）
- 更新 ARCHITECTURE.md（如果改变架构）
- 更新 CHANGELOG.md（记录变更）
- 添加代码注释和文档字符串

## 代码审查

所有 PR 都需要经过代码审查。审查关注：

- 代码质量和可读性
- 测试覆盖率
- 文档完整性
- 是否符合项目设计原则
- 向后兼容性

## 发布流程

由维护者负责：

1. 更新 CHANGELOG.md
2. 更新版本号
3. 创建 git tag
4. 发布到 PyPI

## 行为准则

- 尊重他人
- 接受建设性批评
- 关注对项目最有利的事情
- 对社区成员表现出同理心

## 问题？

如果有任何问题，欢迎：

- 创建 issue
- 在 PR 中讨论
- 联系维护者

感谢你的贡献！
