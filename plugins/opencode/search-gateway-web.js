import { tool } from "@opencode-ai/plugin"

const DEFAULT_BASE = "http://127.0.0.1:8100"
const SEARCH_TIMEOUT_MS = 60_000
const MAX_FETCH_TIMEOUT_MS = 120_000
const RESEARCH_TIMEOUT_MS = 180_000
const DEFAULT_SEARCH_COUNT = 8
const MAX_SEARCH_COUNT = 20

function baseUrl() {
  return (process.env.SEARCH_GATEWAY_URL || DEFAULT_BASE).replace(/\/$/, "")
}

function asStringArray(value) {
  if (value == null) return []
  if (Array.isArray(value)) return value.map((v) => String(v || "").trim()).filter(Boolean)
  const s = String(value).trim()
  return s ? [s] : []
}

function normalizeUrl(raw) {
  const url = String(raw || "").trim()
  if (!url) return ""
  let parsed
  try {
    parsed = new URL(url)
  } catch {
    throw new Error(`invalid url: ${raw}`)
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`invalid url: ${raw}`)
  }
  const host = parsed.hostname.toLowerCase()
  const local =
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "[::1]" ||
    host === "::1" ||
    host.endsWith(".local")
  if (parsed.protocol === "http:" && !local) {
    parsed.protocol = "https:"
  }
  return parsed.toString()
}

async function postJson(path, body, timeoutMs, abort) {
  const ctrl = new AbortController()
  const onAbort = () => ctrl.abort()
  if (abort) {
    if (abort.aborted) ctrl.abort()
    else abort.addEventListener("abort", onAbort, { once: true })
  }
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${baseUrl()}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    })
    const text = await res.text()
    let data
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      throw new Error(`${path} returned non-JSON (HTTP ${res.status})`)
    }
    if (!res.ok) {
      const detail = data?.detail || data?.error || data?.message || text
      throw new Error(`${path} failed (HTTP ${res.status}): ${String(detail).slice(0, 400)}`)
    }
    return data
  } catch (err) {
    if (err?.name === "AbortError") throw new Error(`${path} timed out or aborted`)
    throw err
  } finally {
    clearTimeout(timer)
    if (abort) abort.removeEventListener("abort", onAbort)
  }
}

function formatSearch(data) {
  if (data?.error && !(Array.isArray(data?.results) && data.results.length)) {
    return `Search failed: ${String(data.error).trim()}`
  }
  const results = Array.isArray(data?.results) ? data.results : []
  if (!results.length) return "No results."

  const lines = []
  for (let i = 0; i < results.length; i++) {
    const r = results[i] || {}
    const snippet = String(r.snippet || r.raw || "").trim()
    lines.push(`${i + 1}. ${r.title || "(untitled)"}`)
    if (r.url) lines.push(`   ${r.url}`)
    if (snippet) {
      for (const line of snippet.split("\n")) lines.push(`   ${line}`)
    }
    lines.push("")
  }
  return lines.join("\n").trim()
}

function formatFetch(data, format) {
  const results = Array.isArray(data?.results) ? data.results : []
  if (!results.length) return "No content."

  const parts = []
  for (const r of results) {
    parts.push(`## ${r.title || r.url || "page"}`)
    if (r.url) parts.push(r.url)
    if (r.error) {
      parts.push(`error: ${r.error}`)
      parts.push("")
      continue
    }
    let content = String(r.content || "").trim()
    if (format === "text") {
      content = content
        .replace(/```[\s\S]*?```/g, " ")
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
        .replace(/[#>*_`]/g, " ")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .replace(/[ \t]{2,}/g, " ")
        .trim()
    }
    parts.push(content || "(empty)")
    parts.push("")
  }
  return parts.join("\n").trim()
}

function formatResearch(data) {
  const report = String(data?.report || "").trim()
  const sources = Array.isArray(data?.sources) ? data.sources.filter(Boolean) : []
  const notice = String(data?.notice || "").trim()
  const degraded = Boolean(data?.degraded)
  const lines = []
  if (data?.topic) lines.push(`# ${data.topic}`, "")
  if (degraded || notice) {
    lines.push(`> ${notice || "research degraded to search summary"}`, "")
  }
  lines.push(report || "(empty)")
  if (sources.length) {
    lines.push("", "## sources")
    for (const s of sources) lines.push(`- ${s}`)
  }
  return lines.join("\n").trim()
}

export default async () => {
  return {
    tool: {
      websearch: tool({
        description: [
          "Search the public web and return a ranked list of pages (title, URL, short snippet).",
          "Use when you need information from the open internet: news, product pages, blog posts, GitHub issues, changelogs, RFCs, Stack Overflow, vendor announcements, or any fact that may have changed after your training cutoff.",
          "Also use to discover candidate URLs before reading a full page.",
          "Query tips: be specific (include product/version/error text); use domains to stay on a site (e.g. github.com); use time_range for freshness (day/week/month/year).",
          "Returns snippets only — enough to pick sources, not full article bodies.",
        ].join(" "),
        args: {
          query: tool.schema
            .string()
            .describe("Search query. Prefer concrete terms over vague keywords."),
          count: tool.schema
            .number()
            .optional()
            .describe(`Max hits 1-${MAX_SEARCH_COUNT} (default ${DEFAULT_SEARCH_COUNT})`),
          domains: tool.schema
            .array(tool.schema.string())
            .optional()
            .describe('Only these hosts, e.g. ["github.com","docs.python.org"]'),
          exclude_domains: tool.schema
            .array(tool.schema.string())
            .optional()
            .describe("Hosts to drop from results"),
          time_range: tool.schema
            .enum(["day", "week", "month", "year"])
            .optional()
            .describe("Prefer recently published/updated pages"),
          depth: tool.schema
            .enum(["basic", "advanced"])
            .optional()
            .describe("basic=faster default; advanced=deeper when supported"),
        },
        async execute(args, ctx) {
          const query = String(args.query || "").trim()
          if (!query) throw new Error("query is required")

          const limit = Math.min(
            MAX_SEARCH_COUNT,
            Math.max(1, Math.floor(Number(args.count ?? DEFAULT_SEARCH_COUNT) || DEFAULT_SEARCH_COUNT)),
          )
          const domains = asStringArray(args.domains)
          const exclude_domains = asStringArray(args.exclude_domains)
          const depth = args.depth === "advanced" ? "advanced" : "basic"
          const time_range = args.time_range || undefined

          const body = { query, limit, depth }
          if (domains.length) body.domains = domains
          if (exclude_domains.length) body.exclude_domains = exclude_domains
          if (time_range) body.time_range = time_range

          const data = await postJson("/search", body, SEARCH_TIMEOUT_MS, ctx.abort)
          return {
            title: query,
            output: formatSearch(data),
            metadata: {
              query,
              count: Array.isArray(data?.results) ? data.results.length : 0,
            },
          }
        },
      }),

      webfetch: tool({
        description: [
          "Download one or more web pages and extract the main readable body (article/docs text), stripping chrome like nav and ads.",
          "Use when you already know the URL(s): user pasted a link, or you picked URLs from search results and need the full content to answer accurately.",
          "Good for documentation pages, READMEs, blog posts, release notes, and static HTML articles.",
          "Weak on pages that require login, heavy client-side apps, or CAPTCHA — those often return empty or partial text.",
          "Prefer ≤5 URLs per call (hard max 8). Default output is markdown; use format=text for plain text.",
        ].join(" "),
        args: {
          url: tool.schema.string().optional().describe("Single page URL"),
          urls: tool.schema
            .array(tool.schema.string())
            .optional()
            .describe("Batch of page URLs (prefer ≤5, max 8)"),
          format: tool.schema
            .enum(["markdown", "text"])
            .optional()
            .describe("markdown (default) preserves headings/lists; text is plain"),
          timeout: tool.schema
            .number()
            .optional()
            .describe("Per-call timeout seconds (default 60, max 120)"),
        },
        async execute(args, ctx) {
          const urls = []
          const seen = new Set()
          for (const raw of [args.url, ...asStringArray(args.urls)]) {
            if (!raw) continue
            const u = normalizeUrl(raw)
            if (seen.has(u)) continue
            seen.add(u)
            urls.push(u)
          }
          if (!urls.length) throw new Error("url or urls required")
          if (urls.length > 8) throw new Error("max 8 urls per call")

          const format = args.format === "text" ? "text" : "markdown"
          const timeoutMs = Math.min(
            MAX_FETCH_TIMEOUT_MS,
            Math.max(5_000, Math.floor((Number(args.timeout) || 60) * 1000)),
          )

          const data = await postJson(
            "/extract",
            { urls, format },
            timeoutMs,
            ctx.abort,
          )
          const results = Array.isArray(data?.results) ? data.results : []
          return {
            title: urls.length === 1 ? urls[0] : `${urls.length} pages`,
            output: formatFetch(data, format),
            metadata: {
              urls,
              pages: results.length,
              failed: results.filter((r) => r?.error).length,
            },
          }
        },
      }),

      webresearch: tool({
        description: [
          "Run multi-source web research on a topic and return one synthesized brief (with sources when available).",
          "Use for broad or comparative questions that need more than a single search hit list: landscape overviews, “what are the options”, trade-off summaries, or multi-angle current-event writeups.",
          "Slower than a normal search (often 10–30s+). depth=mini is lighter/faster; depth=pro is deeper; depth=auto lets the backend choose.",
          "Give a clear topic or question, not a bare keyword.",
        ].join(" "),
        args: {
          topic: tool.schema
            .string()
            .describe("Research topic or full question to investigate"),
          depth: tool.schema
            .enum(["auto", "mini", "pro"])
            .optional()
            .describe("auto (default), mini=faster, pro=deeper/slower"),
        },
        async execute(args, ctx) {
          const topic = String(args.topic || "").trim()
          if (!topic) throw new Error("topic is required")
          const depth = ["mini", "pro", "auto"].includes(args.depth) ? args.depth : "auto"

          const data = await postJson(
            "/research",
            { topic, depth },
            RESEARCH_TIMEOUT_MS,
            ctx.abort,
          )
          return {
            title: topic,
            output: formatResearch({ ...data, topic: data?.topic || topic }),
            metadata: {
              topic,
              depth,
              sources: Array.isArray(data?.sources) ? data.sources.length : 0,
            },
          }
        },
      }),
    },
  }
}
