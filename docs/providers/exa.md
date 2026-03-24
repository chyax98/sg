# Exa

> AI 语义搜索引擎，支持 search 和 extract (get_contents) 两种能力。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `exa` |
| 能力 | search, extract |
| API Key | 需要 (`EXA_API_KEY` 或 `EXA_POOL_API_KEY`) |
| 免费额度 | 1,000 次/月 |
| 付费计划 | Pro $10/月起 |
| 官方文档 | https://docs.exa.ai |
| Python SDK | `exa-py` (`pip install exa-py`) |
| API Key 申请 | https://exa.ai |

## Search Gateway 配置

```json
{
  "providers": {
    "exa": {
      "type": "exa",
      "enabled": true,
      "priority": 1,
      "instances": [
        { "id": "exa-1", "api_key": "xxx" }
      ]
    }
  }
}
```

支持 `url` 字段指定自定义 API base URL（通过 `EXA_POOL_BASE_URL` 环境变量）。

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ✅ | 限定搜索域名 |
| `exclude_domains` | ✅ | 排除搜索域名 |
| `time_range` | ✅ | 转为 `start_published_date` ISO 格式 |
| `search_depth` | ✅ | 映射：basic→auto, advanced→deep, fast→fast, ultra-fast→instant |

## Extra 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `type` | `str` | 搜索类型：`auto`(默认), `keyword`, `neural` |
| `category` | `str` | 数据类别：`company`, `research paper`, `news`, `tweet`, `github`, `pdf` 等 |

## SDK 参考 (exa-py)

### 初始化

```python
from exa_py import AsyncExa
exa = AsyncExa(api_key="YOUR_API_KEY")
```

### Search

```python
result = await exa.search(
    query="hottest AI startups",
    num_results=10,
    contents={"highlights": True},       # 返回内容高亮
    include_domains=["github.com"],
    exclude_domains=[],
    start_published_date="2024-01-01",   # ISO 日期
    type="auto",                          # auto | keyword | neural
    category="company",                   # 可选类别过滤
)
# result.results → list of Result(url, title, score, published_date, author, highlights)
```

**Search 关键参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | str | 必填 | 搜索查询 |
| `num_results` | int | 10 | 返回结果数 |
| `include_domains` | list | None | 限定域名 |
| `exclude_domains` | list | None | 排除域名 |
| `start_published_date` | str | None | ISO 格式开始日期 |
| `end_published_date` | str | None | ISO 格式结束日期 |
| `type` | str | `auto` | `auto`/`keyword`/`neural` |
| `category` | str | None | 数据类别过滤 |
| `use_autoprompt` | bool | False | 自动优化查询 |

### Extract (get_contents)

```python
result = await exa.get_contents(
    urls=["https://example.com"],
    text=True,
)
# result.results → list of Result(url, text, title)
```

### search_and_contents

```python
# 搜索并同时获取内容（合并 search + get_contents）
result = await exa.search_and_contents(
    query="AI in healthcare",
    text=True,           # 返回全文
    highlights=True,     # 返回高亮片段
    num_results=5,
)
```
