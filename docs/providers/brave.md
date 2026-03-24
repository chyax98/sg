# Brave Search

> 隐私优先的搜索引擎，通过 REST API 访问，支持搜索操作符和时间过滤。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `brave` |
| 能力 | search |
| API Key | 需要 (`BRAVE_API_KEY`) |
| 免费额度 | 2,000 次/月 |
| 付费计划 | $5/月起 |
| 官方文档 | https://api-dashboard.search.brave.com/documentation |
| SDK | 无官方 SDK，使用 httpx 直接调用 REST API |
| API Key 申请 | https://brave.com/search/api/ |
| Base URL | `https://api.search.brave.com/res/v1` |

## Search Gateway 配置

```json
{
  "providers": {
    "brave": {
      "type": "brave",
      "enabled": true,
      "priority": 2,
      "instances": [
        { "id": "brave-1", "api_key": "BSA-xxx" }
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
| `time_range` | ✅ | 映射到 freshness: day→pd, week→pw, month→pm, year→py |

## Extra 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `country` | `str` | 2字符国家代码，如 `DE`, `US` |
| `search_lang` | `str` | 搜索语言，如 `de`, `en` |
| `freshness` | `str` | 直接 freshness 值（覆盖 time_range），支持自定义日期范围如 `2022-04-01to2022-07-30` |

## API 参考

### Endpoint

```
GET https://api.search.brave.com/res/v1/web/search
```

### Header

```
X-Subscription-Token: <API_KEY>
Accept: application/json
```

### 请求参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `q` | str | 搜索查询（支持 `site:`, `-site:`, `filetype:`, 引号精确匹配） |
| `count` | int | 返回结果数（最大 20） |
| `offset` | int | 分页偏移（最大 9） |
| `freshness` | str | 时间过滤：`pd`(24h), `pw`(7d), `pm`(31d), `py`(1y), 或日期范围 |
| `country` | str | 国家代码 |
| `search_lang` | str | 搜索语言 |
| `extra_snippets` | bool | 每个结果返回最多 5 个额外摘要 |

### 响应格式

```json
{
  "web": {
    "results": [
      {
        "title": "...",
        "url": "...",
        "description": "...",
        "extra_snippets": ["...", "..."]
      }
    ]
  }
}
```

### 搜索操作符

- `site:github.com` — 限定域名
- `-site:medium.com` — 排除域名
- `filetype:pdf` — 文件类型
- `"exact phrase"` — 精确匹配
