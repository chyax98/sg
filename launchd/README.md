# macOS LaunchAgent

让 Search Gateway 开机自启、崩溃拉起，供 OpenCode 插件 `websearch` / `webfetch` 常驻依赖。

## 安装

```bash
# 仓库内
make install-launchd

# 或手动
cp launchd/com.xd.search-gateway.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.xd.search-gateway.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.xd.search-gateway.plist
launchctl enable gui/$(id -u)/com.xd.search-gateway
```

## 卸载

```bash
make uninstall-launchd
```

## 要求

- 已 `uv tool install` / `make install`，存在 `~/.local/bin/search-gateway`
- 配置文件 `~/.sg/config.json`
- 前台模式运行（不要加 `--daemon`）；由 launchd `KeepAlive` 托管

## 检查

```bash
launchctl print gui/$(id -u)/com.xd.search-gateway | head -30
curl -sS http://127.0.0.1:8100/status
tail -f ~/.sg/logs/launchd-stderr.log
```
