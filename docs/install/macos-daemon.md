# macOS daemon 自启

让 Search Gateway 开机自启、崩溃自动拉起。OpenCode 插件 / MCP stdio 之类常驻依赖建议配上。

## 前置

- 已 `uv tool install search-gateway`（见 [uv.md](uv.md)）
- `~/.sg/config.json` 已初始化（`search-gateway init`）
- `which search-gateway` 能找到（通常 `~/.local/bin/search-gateway`）

## 一键安装

```bash
search-gateway daemon install
# 自定义端口
search-gateway daemon install --port 9000
# 强制重装
search-gateway daemon install --force
```

CLI 做的事：

1. 检测平台（仅 macOS 受支持，Linux/Windows 报清晰错误）
2. 解析 `which search-gateway` 真实路径 + `$HOME`
3. 动态生成 plist 写到 `~/Library/LaunchAgents/com.search-gateway.plist`
4. `search-gateway stop` 停掉非 launchd 托管的旧 daemon（避免端口冲突）
5. `launchctl bootstrap` + `enable`
6. curl `/status` 验证启动成功

`make install-launchd` 是 CLI 命令的 alias（Makefile 直接 delegate）。

## 状态

```bash
search-gateway daemon status
```

输出 `launchctl print gui/$UID/com.search-gateway` 的关键字段（state / pid / last exit code / path）+ HTTP `/status` 验证。

## 卸载

```bash
search-gateway daemon uninstall
# 或 make uninstall-launchd
```

卸载会 bootout 服务并删除 plist。

## 验证

```bash
launchctl print gui/$(id -u)/com.search-gateway | head -30
curl -sS http://127.0.0.1:8100/status
tail -f ~/.sg/logs/launchd-stderr.log
```

期望：`/status` 返回 `{"running":true,...}`，stderr log 无 traceback。

## 行为

- `RunAtLoad=true`：开机/登录自启
- `KeepAlive.SuccessfulExit=false`：进程异常退出自动拉起
- `ThrottleInterval=10`：崩溃后至少 10 秒再拉起
- 日志：`~/.sg/logs/launchd-{stdout,stderr}.log` + `~/.sg/logs/gateway.log`
- 端口：默认 8100（`--port` 自定义）

## Label

`com.search-gateway`

## 排错

| 问题 | 解决 |
|---|---|
| `launchctl bootstrap` 失败 | 先 `search-gateway daemon uninstall` 清掉再 install |
| 端口 8100 被占 | `lsof -iTCP:8100`，停掉占用进程；或 `daemon install --port 8101` |
| `/status` 返回 500 | 看 `~/.sg/logs/launchd-stderr.log`，常见是 `~/.sg/config.json` 语法错 |
| 改了代码 daemon 还是旧行为 | editable 模式下，`search-gateway daemon uninstall && daemon install` 让 launchd 重启进程加载新代码 |
