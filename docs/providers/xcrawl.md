# Xcrawl

> Web 爬取和搜索 API，支持 search 和 extract (scrape)，输出 LLM 友好格式。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `xcrawl` |
| 能力 | search, extract |
| API Key | 需要 (`XCRAWL_API_KEY`) |
| 官方文档 | https://docs.xcrawl.com |
| SDK | 无官方 SDK，通过 httpx 调用 REST API |
| API Key 申请 | https://www.xcrawl.com |
| Base URL | `https://run.xcrawl.com` |

## Search Gateway 配置

```json
{
  "providers": {
    "xcrawl": {
      "type": "xcrawl",
      "enabled": true,
      "priority": 5,
      "instances": [
        { "id": "xcrawl-1", "api_key": "xxx" }
      ]
    }
  }
}
```

支持 `url` 字段自定义 Base URL。

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ✅ | 通过 `site:` 操作符 |
| `exclude_domains` | ✅ | 通过 `-site:` 操作符 |
| `time_range` | ❌ | 不支持 |

## Extra 参数

### Search Extra

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `location` | `str` | `US` | 搜索地区 |
| `language` | `str` | `en` | 搜索语言 |

### Extract Extra

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `proxy_location` | `str` | `US` | 代理位置 |
| `locale` | `str` | `en-US` | 页面语言 |
| `device` | `str` | `desktop` | 设备类型 |
| `only_main_content` | `bool` | `false` | 仅提取主要内容 |
| `js_render` | `bool` | `true` | 是否执行 JavaScript |

## API 参考

### Search (SERP) Endpoint

```bash
POST https://run.xcrawl.com/v1/search
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "query": "AI frameworks",
  "limit": 10,
  "location": "US",
  "language": "en"
}
```

**响应格式：**

```json
{
  "search_id": "...",
  "status": "completed",
  "data": {
    "data": [
      {
        "position": 1,
        "title": "...",
        "url": "...",
        "description": "..."
      }
    ]
  }
}
```

### Scrape (Extract) Endpoint

```bash
POST https://run.xcrawl.com/v1/scrape
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "url": "https://example.com",
  "mode": "sync",
  "proxy": {"location": "US"},
  "request": {
    "locale": "en-US",
    "device": "desktop",
    "only_main_content": false
  },
  "js_render": {"enabled": true},
  "output": {
    "formats": ["markdown"]
  }
}
```

**响应格式：**

```json
{
  "scrape_id": "...",
  "status": "completed",
  "data": {
    "markdown": "# Page Title\n...",
    "html": "<html>...</html>",
    "metadata": {
      "title": "Page Title",
      "status_code": 200
    }
  }
}
```

### 其他 Endpoint

| Endpoint | 说明 |
|---|---|
| `POST /v1/crawl` | 全站爬取（异步） |
| `GET /v1/crawl/{id}` | 查询爬取状态和结果 |
| `POST /v1/map` | 列出站点所有 URL |

### 输出格式

| 格式 | 说明 |
|---|---|
| `markdown` | Markdown 格式（默认） |
| `html` | 原始 HTML |
| `json` | 结构化 JSON（AI 提取） |
| `screenshot` | 页面截图 |
