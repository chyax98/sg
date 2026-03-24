# SearXNG

> 自托管的元搜索引擎，免费且不需要 API Key，聚合多个搜索引擎结果。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `searxng` |
| 能力 | search |
| API Key | 不需要 |
| URL | 需要（自建实例地址） |
| 价格 | 完全免费（需自建） |
| 官方文档 | https://docs.searxng.org |
| SDK | 无 SDK，通过 JSON API 调用 |
| 部署指南 | https://docs.searxng.org/admin/installation.html |

## Search Gateway 配置

```json
{
  "providers": {
    "searxng": {
      "type": "searxng",
      "enabled": true,
      "priority": 5,
      "instances": [
        { "id": "searxng-1", "url": "http://localhost:8888" }
      ]
    }
  }
}
```

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ❌ | 不支持（可在 query 中手动加 `site:` 语法） |
| `exclude_domains` | ❌ | 不支持 |
| `time_range` | ✅ | 直接传递 `day`/`month`/`year` |

## API 参考

### Endpoint

```
GET /search?q=...&format=json
POST /search (form data: q=...&format=json)
```

### 请求参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `q` | ✅ | 搜索查询（支持各搜索引擎语法，如 `site:github.com`） |
| `format` | 需要 | 输出格式：`json`/`csv`/`rss`（需在 settings.yml 中启用） |
| `categories` | 可选 | 搜索类别，逗号分隔 |
| `engines` | 可选 | 指定搜索引擎，逗号分隔 |
| `language` | 可选 | 语言代码 |
| `pageno` | 可选 | 页码，默认 1 |
| `time_range` | 可选 | 时间范围：`day`/`month`/`year` |
| `safesearch` | 可选 | 安全搜索：0/1/2 |

### 响应格式

```json
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "...",
      "score": 0.85,
      "engine": "google"
    }
  ],
  "number_of_results": 100
}
```

### Health Check

Search Gateway 通过发送测试查询验证 SearXNG 实例可用性：

```
GET /search?q=test&format=json
```

## 部署注意事项

- SearXNG 的 JSON API 格式需要在 `settings.yml` 中启用
- 默认端口通常为 8888 或 8080
- 许多公共实例禁用了 JSON 格式输出
