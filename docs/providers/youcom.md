# You.com

> 高准确率 AI 搜索引擎（93% SimpleQA），支持 search 和 contents (extract)。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `youcom` |
| 能力 | search, extract |
| API Key | 需要 (`YOUCOM_API_KEY`) |
| 官方文档 | https://documentation.you.com |
| Python SDK | `youdotcom` |
| API Key 申请 | https://you.com |
| Base URL | `https://ydc-index.io` |

## Search Gateway 配置

```json
{
  "providers": {
    "youcom": {
      "type": "youcom",
      "enabled": true,
      "priority": 3,
      "instances": [
        { "id": "youcom-1", "api_key": "xxx" }
      ]
    }
  }
}
```

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ✅ | 通过 `site:` 操作符实现 |
| `exclude_domains` | ✅ | 通过 `-site:` 操作符实现 |
| `time_range` | ✅ | 直接传递 day/week/month/year 到 `freshness` |

## Extra 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `language` | `str` | 搜索语言 |

## API 参考

### Search Endpoint

```
GET https://ydc-index.io/v1/search?query=...&count=10
Header: X-API-Key: <API_KEY>
```

**请求参数：**

| 参数 | 类型 | 说明 |
|---|---|---|
| `query` | str | 搜索查询 |
| `count` | int | 返回结果数 |
| `freshness` | str | 时间过滤 |
| `language` | str | 语言代码 |

**响应格式：**

```json
{
  "results": {
    "web": [
      {
        "url": "...",
        "title": "...",
        "description": "...",
        "snippets": ["...", "..."],
        "thumbnail_url": "...",
        "page_age": "2025-09-06T20:05:44"
      }
    ]
  }
}
```

### Contents Endpoint (Extract)

```
POST https://ydc-index.io/v1/contents
Body: {"urls": ["https://example.com"]}
Header: X-API-Key: <API_KEY>
```

**响应格式：**

```json
[
  {
    "url": "...",
    "html": "..."
  }
]
```
