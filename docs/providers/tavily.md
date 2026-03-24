# Tavily

> AI 优化搜索引擎，支持 search、extract、research 三种能力。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `tavily` |
| 能力 | search, extract, research |
| API Key | 需要 (`TAVILY_API_KEY`) |
| 免费额度 | 1,000 次/月 |
| 付费计划 | Pro $29/月起 |
| 官方文档 | https://docs.tavily.com |
| Python SDK | `tavily-python` (`pip install tavily-python`) |
| API Key 申请 | https://tavily.com |

## Search Gateway 配置

```json
{
  "providers": {
    "tavily": {
      "type": "tavily",
      "enabled": true,
      "priority": 1,
      "instances": [
        { "id": "tavily-1", "api_key": "tvly-xxx" }
      ]
    }
  }
}
```

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ✅ | 限定搜索域名 |
| `exclude_domains` | ✅ | 排除搜索域名 |
| `time_range` | ✅ | `day`, `week`, `month`, `year` |
| `search_depth` | ✅ | `basic` (1 credit) / `advanced` (2 credits) |

## Extra 参数

通过 `extra` 字段传递的 Tavily 特有参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `topic` | `str` | 搜索类别：`general`(默认), `news`, `finance` |
| `include_images` | `bool` | 返回结果中包含图片 |
| `include_raw_content` | `bool` | 返回完整原始页面内容 |

## SDK 参考 (tavily-python)

### 初始化

```python
from tavily import AsyncTavilyClient
client = AsyncTavilyClient(api_key="tvly-YOUR_API_KEY")
```

### Search

```python
result = await client.search(
    query="Python async programming",
    search_depth="basic",       # basic | advanced
    max_results=10,             # 1-20
    include_domains=["python.org"],
    exclude_domains=[],
    time_range="week",          # day | week | month | year
    topic="general",            # general | news | finance
)
# result["results"] → list of {title, url, content, score, raw_content}
```

**Search 关键参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | str | 必填 | 搜索查询 |
| `search_depth` | str | `basic` | `basic` 或 `advanced` |
| `max_results` | int | 5 | 1-20 |
| `include_domains` | list | [] | 限定域名 |
| `exclude_domains` | list | [] | 排除域名 |
| `time_range` | str | None | `day`/`week`/`month`/`year` |
| `topic` | str | `general` | `general`/`news`/`finance` |
| `include_answer` | bool | False | 生成 LLM 回答 |
| `include_raw_content` | bool | False | 返回原始页面 |
| `chunks_per_source` | int | 3 | 每个来源的内容片段数（仅 advanced） |

### Extract

```python
result = await client.extract(urls=["https://example.com"])
# result["results"] → list of {url, raw_content}
```

### Research

Search Gateway 通过 `search(search_depth="advanced")` 实现 research 功能，根据 depth 控制结果数：

- `mini` → 5 results
- `auto` → 10 results
- `pro` → 20 results
