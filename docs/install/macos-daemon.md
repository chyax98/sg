# macOS daemon 自启

让 Search Gateway 开机自启、崩溃自动拉起。OpenCode 插件 / MCP stdio 之类常驻依赖建议配上。

## 前置

- 已 `uv tool install search-gateway`（见 [uv.md](uv.md)）
- `~/.sg/config.json` 已初始化（`search-gateway init`）
- `which search-gateway` 能找到（通常 `~/.local/bin/search-gateway`）

## 安装

### 方式 1：make（仓库内）

```bash
git clone https://github.com/chyax98/sg
cd sg
make install-launchd
```

`make install-launchd` 做的事：
1. 拷 `launchd/com.xd.search-gateway.plist` 到 `~/Library/LaunchAgents/`
2. `launchctl bootout` 旧实例（若有）
3. 停掉非 launchd 托管的旧进程（避免端口冲突）
4. `launchctl bootstrap` + `enable`
5. curl `/status` 验证启动成功

### 方式 2：手动

```bash
mkdir -p ~/Library/LaunchAgents ~/.sg/logs
cp launchd/com.xd.search-gateway.plist ~/Library/LaunchAgents/

launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.xd.search-gateway.plist 2>/dev/null || true
search-gateway stop 2>/dev/null || true

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.xd.search-gateway.plist
launchctl enable gui/$(id -u)/com.xd.search-gateway
```

> 计划中：`search-gateway daemon install` CLI 跨平台抽象（macOS launchd / Linux systemd / Windows schtasks）。当前阶段用 make。

## 验证

```bash
launchctl print gui/$(id -u)/com.xd.search-gateway | head -30
curl -sS http://127.0.0.1:8100/status
tail -f ~/.sg/logs/launchd-stderr.log
```

期望：`/status` 返回 `{"running":true,...}`，stderr log 无 traceback。

## 行为

- `RunAtLoad=true`：开机/登录自启
- `KeepAlive=true`：崩溃自动拉起
- 日志：`~/.sg/logs/launchd-{stdout,stderr}.log`
- 端口：默认 8100（plist 模板，未来 `daemon install` 会动态生成）

## 卸载

```bash
# 仓库内
make uninstall-launchd

# 或手动
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.xd.search-gateway.plist
rm ~/Library/LaunchAgents/com.xd.search-gateway.plist
```

## 排错

| 问题 | 解决 |
|---|---|
| `launchctl bootstrap` 失败 | 先 `launchctl bootout gui/$(id -u) .../com.xd.search-gateway.plist` 清旧 |
| 端口 8100 被占 | `lsof -iTCP:8100`，停掉占用进程；或改 plist 里的端口 |
| `/status` 返回 500 | 看 `~/.sg/logs/launchd-stderr.log`，常见是 `~/.sg/config.json` 语法错 |
| 改了 plist 不生效 | 必须 `bootout` 再 `bootstrap`，不能只 `kickstart` |
| daemon 跑的是旧代码 | editable 模式下，`stop && start` 让进程重启加载新代码 |

## Label 说明

当前 plist 的 Label 是 `com.xd.search-gateway`（历史命名）。**计划改成 `com.search-gateway`**（去个人化），届时需要：

```bash
make uninstall-launchd          # 卸旧 Label
# 升级到新版本后
make install-launchd            # 装新 Label
```
