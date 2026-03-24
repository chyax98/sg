# Firecrawl

> Web 内容抓取和搜索服务，支持 search 和 extract (scrape)，输出干净的 Markdown。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `firecrawl` |
| 能力 | search, extract |
| API Key | 需要 |
| 免费额度 | 500 次/月 |
| 官方文档 | https://docs.firecrawl.dev |
| Python SDK | `firecrawl-py` (`pip install firecrawl-py`) |
| API Key 申请 | https://firecrawl.dev |

## Search Gateway 配置

```json
{
  "providers": {
    "firecrawl": {
      "type": "firecrawl",
      "enabled": true,
      "priority": 5,
      "instances": [
        { "id": "firecrawl-1", "api_key": "fc-xxx" }
      ]
    }
  }
}
```

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ✅ | 通过 `site:` 操作符 |
| `exclude_domains` | ✅ | 通过 `-site:` 操作符 |
| `time_range` | ✅ | 映射到 Google `tbs` 参数 |

## SDK 参考 (firecrawl-py)

### 初始化

```python
from firecrawl import AsyncFirecrawl
firecrawl = AsyncFirecrawl(api_key="fc-YOUR-API-KEY")
```

### Search

```python
results = await firecrawl.search(
    query="AI frameworks",
    limit=10,
    tbs="qdr:w",     # 时间过滤：qdr:d(天), qdr:w(周), qdr:m(月), qdr:y(年)
)
# → list or {"data": [...]} 
# 每个结果含 title, url, markdown/content/description, score
```

### Scrape (Extract)

```python
result = await firecrawl.scrape_url(
    "https://example.com",
    formats=["markdown"],    # markdown | html
)
# → {markdown: "...", metadata: {title: "..."}}
```

### Crawl

```python
job = await firecrawl.crawl(
    url="https://docs.example.com",
    limit=100,
    scrape_options={"formats": ["markdown", "html"]},
)
```

### Map

```python
urls = await firecrawl.map(url="https://example.com", limit=10)
```

### 主要功能

| 功能 | 说明 |
|---|---|
| scrape | 单页抓取，返回 Markdown/HTML/screenshot |
| crawl | 全站爬取（异步），支持 sitemap |
| map | 列出站点所有 URL |
| search | 关键词搜索 |
