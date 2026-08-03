# Search Gateway 标准协议

Gateway / Plugin / CLI 只认本协议。Provider Adapter 负责与各 SDK 互转。

## 分层

```text
Client (OpenCode plugin / HTTP / CLI / SDK)
        │  标准请求 Spec
        ▼
     Gateway  ── 校验、按 Capability 投影、failover
        │  同一套 Spec / Result
        ▼
  Provider Adapter  ── 只做 SDK kwargs ↔ 协议字段
        │
     上游 SDK / HTTP
```

## Capability

每个 provider 声明自己支持什么；**未声明的字段不得静默传给 SDK**。

| 能力块 | 字段 |
|--------|------|
| ops | `search` / `extract` / `research` |
| search | `domains`, `exclude_domains`, `time_range`, `depth`, `language`, `location`, `raw_content` |
| extract | `formats[]`, `multi_url`, `only_main` |
| research | `depths[]`（如 mini/pro/auto） |

Gateway 入站策略：

1. 未知 op → 错误  
2. 请求字段超出 capability → **strip** 并写入响应 `warnings`（不整请求失败，利于 failover）  
3. Adapter 内再做 SDK 必填校验  

## 请求 Spec

### SearchSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| query | str | 必填 |
| limit | int 1–50 | 默认 10；HTTP 兼容 `max_results` |
| domains | str[] | include |
| exclude_domains | str[] | |
| time_range | day\|week\|month\|year | |
| depth | basic\|advanced\|fast\|ultra-fast | 默认 basic |
| language | str? | |
| location | str? | |
| want_raw | bool | 是否要原文级内容 |
| provider | str? | 指定 group/instance |
| vendor | object? | 厂商扩展，默认忽略 |

### ExtractSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| urls | str[] | 必填 |
| format | markdown\|text\|html | 默认 markdown |
| only_main | bool? | 只要主内容 |
| provider | str? | |
| vendor | object? | |

### ResearchSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| topic | str | 必填 |
| depth | auto\|mini\|pro | 默认 auto |
| provider | str? | |
| vendor | object? | |

## 响应 Result

### 公共 envelope

`provider`, `latency_ms`, `warnings[]`, 可选 `result_file`（日志路径，非 agent 主路径）

### Search

- hits[]: `title`, `url`, `snippet`（必有）, `score?`, `published_at?`, `author?`, `raw?`
- `query`, `total`

### Extract

- results[]: `url`, `title?`, `content`, `error?`

### Research

- `topic`, `report`, `sources[]`（url 列表）

## Adapter 职责

1. Spec → SDK 调用参数（只映射 capability 内字段）  
2. SDK 响应 → 标准 Result（统一走 assemble 辅助）  
3. 不写历史、不做 failover、不读配置池  

## Executor 语义（实现约定，非 HTTP 字段）

面向本地免费 key 池：

- **组内**：`selection=round_robin|random|priority` 选 instance  
- **组间**：按 group `priority` 失败切换  
- **空结果 = 失败**：search `results=[]`、extract 全部 error/空正文、research 空 `report` → 记失败并换下一 instance/group  
- **fallback_for**：能力级兜底（如 search→duckduckgo，extract→jina），主链路耗尽后再试  
- **max_attempts**：`<=0` 试完全部候选 group；`>0` 限制组数  
- Agent 工具输出只含任务正文；`provider` / 熔断状态给人用 CLI/`/providers`，不进工具 schema  

## 版本

协议随 `search-gateway` 发行；破坏性变更记 CHANGELOG。
