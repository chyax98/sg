# 源码安装（开发者）

适合给 sg 提 PR、改 provider、跑测试。

## 前置

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- git

## 一行安装（editable 模式）

```bash
git clone https://github.com/chyax98/sg
cd sg
uv tool install --editable .
```

editable 模式下改 `src/sg/` 代码立即生效，无需重装。

## 验证

```bash
search-gateway --help
make test                          # pytest 全跑
uv run mypy src/sg                 # 类型检查
uv run ruff check .                # lint
```

## 开发循环

```bash
# 跑单个测试
uv run pytest tests/test_context7.py -v

# 改完代码：重启 daemon 让新代码生效（editable 模式仍需重启进程）
search-gateway stop && search-gateway start --daemon

# 提交前质量门禁
make test && uv run ruff check . && uv run ruff format --check . && uv run mypy src/sg
```

## 打包检查

force-include 的资源（`plugins/opencode/` → `sg/_plugins_data/`）只有 build wheel 时复制，editable 模式下 cli.py 用双路径回退找仓库源。验证 wheel 内容：

```bash
uv build
unzip -l dist/search-gateway-*.whl | grep -E "_plugins_data|share/search-gateway"
```

应该看到：
- `sg/_plugins_data/search-gateway-web.js`
- `sg/_plugins_data/search-gateway-context7.js`
- `share/search-gateway/web/...`
- `share/search-gateway/prompts/...`

## 调试 daemon

```bash
# 前台启动看实时日志
search-gateway start --log-level DEBUG

# 跟踪日志
tail -f ~/.sg/logs/gateway.log

# 看 daemon 跑的是不是当前工作区代码
ls -la $(python3 -c "import sg; print(sg.__file__)")
# editable: 应指向 ~/gh-repo/sg/src/sg/__init__.py
# 非 editable: 指向 ~/.local/share/uv/tools/search-gateway/...
```

## 提 PR

见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。提交前确认：

- [ ] `make test` 通过
- [ ] `ruff check .` + `ruff format --check .` 通过
- [ ] `mypy src/sg` 通过（新代码必须 0 error）
- [ ] 新加的 provider 有 `docs/providers/<name>.md`
- [ ] CHANGELOG.md `[Unreleased]` 段补条目
