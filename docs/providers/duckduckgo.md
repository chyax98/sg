# DuckDuckGo

> 免费搜索引擎，无需 API Key，作为默认 fallback provider。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `duckduckgo` |
| 能力 | search |
| API Key | 不需要 |
| 价格 | 完全免费 |
| Python 库 | `ddgs` (`pip install ddgs`) |
| 源码 | https://github.com/deedy5/ddgs |
| 搜索引擎 | 支持 bing, brave, duckduckgo, google, mojeek, yandex, yahoo, wikipedia 等后端 |

## Search Gateway 配置

DuckDuckGo 默认自动作为 fallback provider 注入（无需手动配置）。如需显式配置：

```json
{
  "providers": {
    "duckduckgo": {
      "type": "duckduckgo",
      "enabled": true,
      "priority": 100,
      "fallback_for": ["search"],
      "instances": [
        { "id": "duckduckgo" }
      ]
    }
  }
}
```

## 支持的搜索参数

| 参数 | 支持 | 说明 |
|---|---|---|
| `include_domains` | ❌ | 不支持 |
| `exclude_domains` | ❌ | 不支持 |
| `time_range` | ✅ | 映射：day→d, week→w, month→m, year→y |

## Extra 参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `region` | `str` | 地区代码，如 `us-en`, `uk-en`, `ru-ru` |

## Library 参考 (ddgs)

### DDGS 类

```python
from ddgs import DDGS
ddgs = DDGS(proxy=None, timeout=5)
```

### text() 方法

```python
results = DDGS().text(
    query="python programming",
    region="us-en",          # 地区代码
    safesearch="moderate",   # on | moderate | off
    timelimit="y",           # d(天) | w(周) | m(月) | y(年)
    max_results=10,
    backend="auto",          # auto | bing | brave | duckduckgo | google | ...
)
# → list of {"title": "...", "href": "...", "body": "..."}
```

**text() 参数：**

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | str | 必填 | 搜索查询 |
| `region` | str | `us-en` | 地区代码 |
| `safesearch` | str | `moderate` | 安全搜索级别 |
| `timelimit` | str | None | 时间限制 d/w/m/y |
| `max_results` | int | 10 | 最大结果数 |
| `backend` | str | `auto` | 搜索后端引擎 |

### 其他方法

ddgs 还支持 `images()`, `videos()`, `news()`, `books()` 方法，但 Search Gateway 目前只使用 `text()`。

> **注意**：ddgs 的 `text()` 是同步方法，Search Gateway 通过 `asyncio.to_thread()` 包装为异步调用。
