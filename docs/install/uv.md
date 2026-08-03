# uv install（推荐）

终端用户最快上手方案。需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

## 一行安装

```bash
uv tool install search-gateway
```

> 仓库内安装：`git clone https://github.com/chyax98/sg && cd sg && uv tool install .`

## 验证

```bash
search-gateway --help            # 列所有命令
which search-gateway             # 通常 ~/.local/bin/search-gateway
```

## 初始化配置

```bash
search-gateway init              # 创建 ~/.sg/config.json
vim ~/.sg/config.json            # 加 API key（可选）
```

不配任何 key 时默认用 DuckDuckGo（免费，自动 fallback）。

## 启动 daemon

```bash
search-gateway start --daemon    # 后台启动，监听 127.0.0.1:8100
search-gateway status            # 验证 running=True
```

## 冒烟测试

```bash
search-gateway search "test query" -n 3
curl -s http://127.0.0.1:8100/status | python3 -m json.tool
```

## 下一步：选一种集成方式

| 集成 | 命令 |
|---|---|
| AI 助手读 SKILL | `search-gateway skill get` |
| AI 引导式配置 | `search-gateway setup` |
| OpenCode 插件 | `search-gateway plugin install && search-gateway plugin setup` |
| Claude Code MCP | `claude mcp add search-gateway stdio search-gateway mcp` |

## 升级

```bash
uv tool install --upgrade search-gateway
# 仓库内：cd sg && git pull && uv tool install --force .
```

## 卸载

```bash
search-gateway stop
uv tool uninstall search-gateway
rm -rf ~/.sg                  # 可选：清配置和历史
```

## 排错

| 问题 | 解决 |
|---|---|
| `search-gateway: command not found` | `~/.local/bin` 不在 PATH，加 `export PATH="$HOME/.local/bin:$PATH"` 到 shell rc |
| 启动报端口占用 | `search-gateway stop` 再 start，或 `start --port 8101` |
| `~/.sg/config.json: not found` | 跑 `search-gateway init` |
| DuckDuckGo 慢/被限 | 配 Tavily / Exa 等付费 provider，见 `docs/providers/` |
