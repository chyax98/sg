# macOS LaunchAgent

让 Search Gateway 开机自启、崩溃拉起，供 OpenCode 插件 / MCP stdio 常驻依赖。

## 安装

```bash
search-gateway daemon install
# 自定义端口
search-gateway daemon install --port 9000
# 强制重装
search-gateway daemon install --force
```

CLI 动态生成 plist，自动用 `which search-gateway` 和 `$HOME` 适配真实路径——仓库内**不再维护静态 plist 文件**。

`make install-launchd` 等价于 `search-gateway daemon install`（Makefile target 直接 delegate 给 CLI）。

## 状态

```bash
search-gateway daemon status
# 显示 launchctl print 关键字段 + HTTP /status 验证
```

## 卸载

```bash
search-gateway daemon uninstall
# 或 make uninstall-launchd
```

bootout 服务并删除 plist。

## Label

`com.search-gateway`

## 行为

- `RunAtLoad=true`：开机/登录自启
- `KeepAlive.SuccessfulExit=false`：进程异常退出自动拉起
- `ThrottleInterval=10`：崩溃后至少间隔 10 秒再拉起，避免疯狂重启
- 日志：`~/.sg/logs/launchd-{stdout,stderr}.log` + `~/.sg/logs/gateway.log`
- 端口：默认 8100，可 `--port` 自定义

## 要求

- 已 `uv tool install search-gateway`（见 [../docs/install/uv.md](../docs/install/uv.md)）
- `~/.sg/config.json` 已初始化（`search-gateway init`）
- `which search-gateway` 能找到（通常 `~/.local/bin/search-gateway`）

## 排错

```bash
# 看 launchd 日志
tail -f ~/.sg/logs/launchd-stderr.log

# 看 daemon 自己的日志
tail -f ~/.sg/logs/gateway.log

# 验证 daemon HTTP
curl -sS http://127.0.0.1:8100/status

# 详细 launchctl 状态
launchctl print gui/$(id -u)/com.search-gateway | head -40
```
