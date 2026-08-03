# Context7

> 库文档旁路：解析 library ID + 拉取 docs snippets。与 web search/extract/research **无关**。

对齐官方 MCP（`@upstash/context7-mcp`）：

| MCP 工具 | HTTP | 上游 API |
|----------|------|----------|
| `resolve-library-id` | `POST /docs/search` | `GET /api/v2/libs/search` |
| `query-docs` | `POST /docs/context` | `GET /api/v2/context` |

## 配置（多 key）

```json
{
  "providers": {
    "context7": {
      "type": "context7",
      "enabled": true,
      "priority": 10,
      "selection": "random",
      "defaults": { "timeout": 60000 },
      "instances": [
        { "id": "context7-1", "api_key": "ctx7sk-..." },
        { "id": "context7-2", "api_key": "ctx7sk-..." }
      ]
    }
  }
}
```

- `selection`: `random`（推荐）或 `round_robin` — 组内多 key 分流
- 单次请求内某 key **HTTP 失败** → executor 换同组下一把 key
- 连续失败 → **熔断**暂时禁用该 instance（与其它 provider 同一套 CB）
- 库名搜不到（空列表）算正常结果，不换 key、不熔断

## 请求体

`POST /docs/search`

```json
{ "library_name": "Next.js", "query": "app router middleware" }
```

`POST /docs/context`

```json
{ "library_id": "/vercel/next.js", "query": "middleware authentication" }
```

API key：https://context7.com/dashboard
