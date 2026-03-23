# Search Gateway 项目规则

## 项目概述

Search Gateway 是一个为 AI 设计的统一搜索网关，提供多提供商自动故障转移、账号池化管理、熔断器保护。

**核心特性**：
- 8 种搜索 Provider（Tavily, Exa, Brave, You.com, Firecrawl, Jina, SearXNG, DuckDuckGo）
- Provider Group + Instance Pool 架构
- Circuit Breaker 熔断器保护
- HTTP REST API + MCP 协议 + CLI + Python SDK

## 项目结构

```
search-gateway/
├── src/sg/              # 源代码
│   ├── cli/             # CLI 命令实现
│   ├── models/          # Pydantic 数据模型
│   ├── providers/       # Provider 实现（每个 provider 一个文件）
│   │   ├── base.py      # Provider 基类和接口
│   │   ├── registry.py  # Provider 注册表
│   │   └── *.py         # 具体 provider 实现
│   ├── server/          # HTTP/MCP 服务器
│   │   ├── gateway.py   # Gateway 核心逻辑
│   │   ├── executor.py  # 路由和熔断器
│   │   ├── http_server.py  # HTTP REST API
│   │   └── mcp_server.py   # MCP 服务器
│   └── sdk/             # Python SDK
├── tests/               # 测试
├── docs/                # 文档（最小化）
├── scripts/             # 开发脚本
├── Makefile             # 开发工具
├── README.md            # 完整用户文档（自包含）
├── ARCHITECTURE.md      # 架构设计文档（自包含）
├── CONTRIBUTING.md      # 贡献指南
├── CHANGELOG.md         # 更新日志
└── LICENSE              # MIT 许可证
```

## 代码规范

### Python 代码风格

- **Python 版本**：3.12+
- **代码风格**：遵循 PEP 8，使用 ruff 格式化
- **类型注解**：所有函数必须有类型注解
- **文档字符串**：公共 API 必须有 docstring

### 命名规范

- **文件名**：小写 + 下划线（`provider_name.py`）
- **类名**：大驼峰（`SearchProvider`）
- **函数/变量**：小写 + 下划线（`search_query`）
- **常量**：大写 + 下划线（`MAX_RESULTS`）

### 导入顺序

```python
# 1. 标准库
import asyncio
from pathlib import Path

# 2. 第三方库
from pydantic import BaseModel
import httpx

# 3. 本地模块
from ..models.config import Config
from .base import SearchProvider
```

## 架构原则

### 1. 两层路由架构

```
请求 → Executor → Provider Group 选择 → Instance 选择 → 执行
```

- **外层**：在 Provider Group 之间选择（failover/round_robin/random）
- **内层**：在 Group 内的 Instance 之间选择（random/round_robin/priority）

### 2. 熔断器设计

- **作用域**：每个 Instance 独立的熔断器
- **状态**：CLOSED → OPEN → HALF_OPEN → CLOSED
- **失败分类**：
  - 瞬态错误（500, timeout）：指数退避
  - 配额错误（429）：固定 24h
  - 认证错误（401, 403）：固定 7 天

### 3. 历史记录

- **强制开启**：所有搜索结果必须保存到文件
- **文件路径**：`~/.sg/history/YYYY-MM/timestamp-uuid.json`
- **返回格式**：返回文件路径 + 元数据（大小、行数、字数）

## 开发工作流

### 添加新 Provider

1. 在 `src/sg/providers/` 创建新文件（如 `my_provider.py`）
2. 继承 `SearchProvider` 基类
3. 声明 `ProviderInfo`：
   ```python
   class MyProvider(SearchProvider):
       info = ProviderInfo(
           type="my_provider",
           display_name="My Provider",
           capabilities=("search",),  # search, extract, research
       )
   ```
4. 实现必要方法：
   - `async def initialize()` - 初始化（可选）
   - `async def shutdown()` - 清理（可选）
   - `async def search(query, **kwargs)` - 搜索实现
5. 在 `registry.py` 的 `_register_builtins()` 注册
6. 添加测试到 `tests/test_providers.py`

### 开发模式安装

```bash
# 推荐：开发模式（代码修改自动生效）
make dev

# 或手动
uv tool install --editable .
```

### 快速更新流程

```bash
# 方式一：使用 Makefile
make update    # 提交、推送、重新安装

# 方式二：手动
git add -A && git commit -m "feat: xxx" && git push && uv tool install --force .
```

### 测试

```bash
# 运行所有测试
make test

# 或手动
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=src/sg --cov-report=html
```

## 重要约定

### 1. 配置管理

- **配置文件位置**：`~/.sg/config.json`（全局唯一）
- **不支持项目级配置**：避免配置分散
- **配置热重载**：支持运行时通过 API 修改配置

### 2. 错误处理

- **不捕获所有异常**：只捕获预期的异常
- **错误分类**：区分瞬态、配额、认证错误
- **错误传播**：Instance 失败 → Group 失败 → Fallback → 抛出错误

### 3. 日志规范

- **级别**：DEBUG（详细执行流程）、INFO（关键操作）、ERROR（错误）
- **格式**：`YYYY-MM-DD HH:MM:SS [LEVEL] module: message`
- **关键日志点**：
  - Provider 选择
  - 熔断器状态变更
  - 请求成功/失败
  - 配置重载

### 4. 向后兼容

- **开发阶段不做向后兼容**：直接删、直接改、直接重写
- **不保留旧接口**：不写兼容层、不加 deprecated 标记
- **不确定是否被用？**：删掉，让编译/测试报错告诉你

## 文档规范

### 文档结构

- **README.md**：完整的用户文档，自包含，不引用其他文档
- **ARCHITECTURE.md**：架构设计文档，自包含
- **CONTRIBUTING.md**：贡献指南
- **CHANGELOG.md**：遵循 [Keep a Changelog](https://keepachangelog.com/) 格式

### 文档原则

- **自包含**：每个文档独立完整，不相互引用
- **当前状态**：只描述"现在是什么"，不记录"以前是什么"
- **git 记录历史**：过期文档直接删，需要时 `git checkout` 历史版本

### CHANGELOG 规范

每次有意义变更必更新：

- **分类**：Added / Changed / Deprecated / Removed / Fixed / Security
- **写给用户看**：说明影响，不是罗列 commit
- **Breaking changes**：必须醒目标注并附迁移说明

## 提交规范

### Commit Message 格式

```
<type>: <subject>

<body>
```

**类型**：
- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

**示例**：
```
feat: add MCP SSE mode support

- Mount MCP SSE endpoint at /mcp/sse for persistent gateway instance
- Support multiple clients sharing same gateway (providers init once)
- Update README with SSE mode configuration
```

## 常见任务

### 启动开发服务器

```bash
sg start              # 启动 HTTP 服务器（端口 8100）
sg start --port 9000  # 自定义端口
```

### 测试 MCP 集成

```bash
# stdio 模式
sg mcp

# SSE 模式（先启动服务器）
sg start
# 然后配置 Claude Desktop 连接到 http://127.0.0.1:8100/mcp/sse
```

### 查看状态

```bash
sg status      # Gateway 状态
sg providers   # Provider 列表及熔断器状态
sg health      # 运行健康检查
sg history     # 搜索历史
```

### 调试

```bash
# 设置日志级别
export SG_LOG_LEVEL=DEBUG
sg start

# 查看日志
tail -f ~/.sg/logs/gateway.log
```

## 性能考虑

- **异步优先**：所有 I/O 操作使用 async/await
- **并发控制**：使用 `asyncio.Semaphore` 限制并发
- **超时设置**：所有网络请求必须设置超时
- **资源清理**：使用 `async with` 确保资源释放

## 安全考虑

- **API Key 保护**：配置文件权限 600
- **输入验证**：使用 Pydantic 验证所有输入
- **错误信息**：不泄露敏感信息（API Key、内部路径）
- **依赖更新**：定期更新依赖，修复安全漏洞

## 发布流程

1. 更新 `CHANGELOG.md`
2. 更新版本号（`pyproject.toml`）
3. 创建 git tag：`git tag v3.x.x`
4. 推送：`git push && git push --tags`
5. 发布到 PyPI（由维护者执行）

## 问题排查

### Provider 一直失败

1. 检查熔断器状态：`sg providers`
2. 查看日志：`~/.sg/logs/gateway.log`
3. 运行健康检查：`sg health`
4. 检查 API Key 配置

### MCP 连接失败

1. 检查 `sg` 命令是否在 PATH：`which sg`
2. 手动测试：`sg mcp`
3. 检查配置文件：`ls ~/.sg/config.json`
4. 查看 Claude Desktop 日志

### 配置不生效

1. 确认配置文件位置：`~/.sg/config.json`
2. 验证 JSON 格式：`python -m json.tool ~/.sg/config.json`
3. 重载配置：`curl -X POST http://localhost:8100/api/config/reload`
4. 重启服务器：`sg stop && sg start`
