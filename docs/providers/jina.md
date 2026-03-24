# Jina Reader

> 免费 URL 内容提取服务，支持 extract（免费）和 search（需 API Key）。

## 基本信息

| 项目 | 说明 |
|---|---|
| 类型 | `jina` |
| 能力 | extract（免费）, search（需 key） |
| API Key | 可选（extract 免费，search 需要） |
| 价格 | Extract 免费，Search 付费 |
| 官方文档 | https://jina.ai/reader/ |
| SDK | 无官方 SDK，通过 URL 前缀 API 调用 |
| API 文档 | https://r.jina.ai/docs |
| 源码 | https://github.com/jina-ai/reader |

## Search Gateway 配置

```json
{
  "providers": {
    "jina": {
      "type": "jina",
      "enabled": true,
      "priority": 10,
      "instances": [
        { "id": "jina-1" }
      ]
    }
  }
}
```

如需 search 能力，需要提供 API key：

```json
{ "id": "jina-1", "api_key": "jina_xxx" }
```

## API 参考

### Extract (r.jina.ai) — 免费

将任意 URL 转为 LLM 友好格式，只需在 URL 前加 `r.jina.ai`：

```bash
curl https://r.jina.ai/https://example.com \
  -H "Accept: application/json"
```

**响应格式：**

```json
{
  "data": {
    "title": "Example Domain",
    "content": "# Example Domain\nThis domain is for use...",
    "url": "https://example.com"
  }
}
```

**支持的 Header 参数：**

| Header | 说明 |
|---|---|
| `Accept: application/json` | JSON 格式响应（含 url, title, content） |
| `X-No-Cache: true` | 绕过缓存 |
| `X-Timeout: 30` | 超时秒数 |
| `X-Target-Selector: article` | CSS 选择器提取指定元素 |
| `X-Wait-For-Selector: .content` | 等待元素出现后提取 |
| `X-Remove-Selector: nav,footer` | 移除指定元素 |
| `X-With-Images: true` | 保留图片信息 |
| `X-With-Links-Summary: true` | 生成链接摘要 |
| `X-Proxy-Country: US` | 使用指定国家代理 |
| `Authorization: Bearer jina_xxx` | API Key（提高速率限制） |

### Search (s.jina.ai) — 需 API Key

```bash
curl https://s.jina.ai/your+search+query \
  -H "Accept: application/json" \
  -H "Authorization: Bearer jina_xxx"
```

**响应格式：**

```json
{
  "data": [
    {
      "title": "...",
      "url": "...",
      "content": "..."
    }
  ]
}
```

## 特殊功能

| 功能 | 说明 |
|---|---|
| ReaderLM-v2 | 使用专用模型转换 HTML→Markdown（质量更高，消耗 3x token） |
| Image Caption | 自动为图片生成描述 |
| Stream Mode | 流式返回，适合大页面 |
| GFM | 支持 GitHub Flavored Markdown 输出 |
