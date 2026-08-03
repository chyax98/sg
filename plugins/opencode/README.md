# OpenCode plugins for Search Gateway

把 Search Gateway 暴露成 OpenCode 的 `websearch` / `webfetch` / `webresearch` / `resolve-library-id` / `query-docs` 工具。插件是纯 JS，运行时通过 HTTP 调用本地 gateway daemon（默认 `http://127.0.0.1:8100`）。

## 文件

| 文件 | 提供工具 | 调用端点 |
|---|---|---|
| `search-gateway-web.js` | `websearch` / `webfetch` / `webresearch` | `/search` / `/extract` / `/research` |
| `search-gateway-context7.js` | `resolve-library-id` / `query-docs` | `/docs/search` / `/docs/context` |

## 安装

推荐用 CLI：

```bash
search-gateway plugin install
# 默认装到 ~/.config/opencode/plugins/

# 自定义目录
search-gateway plugin install --path /path/to/plugins

# 强制覆盖
search-gateway plugin install --force
```

然后在 `opencode.json` 的 `plugin` 数组里引用：

```json
{
  "plugin": [
    "/Users/<you>/.config/opencode/plugins/search-gateway-web.js",
    "/Users/<you>/.config/opencode/plugins/search-gateway-context7.js"
  ]
}
```

重启 opencode 生效。

> `~/.config/opencode/plugins/` 目录下的 .js 文件会被 opencode 自动发现，但显式声明在 `plugin` 数组里行为更明确（与同目录其他插件一致）。

## 依赖

- Search Gateway daemon 运行在 `http://127.0.0.1:8100`（可用 `SEARCH_GATEWAY_URL` 覆盖）
- Context7 provider 已在 `~/.sg/config.json` 配置（`docs_search` / `docs_context` 才有效）

## 自定义

- daemon URL：设环境变量 `SEARCH_GATEWAY_URL=http://host:port`
- 改插件行为直接编辑本目录的 .js，重启 opencode 即可
