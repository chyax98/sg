import { tool } from "@opencode-ai/plugin"

const DEFAULT_BASE = "http://127.0.0.1:8100"
const TIMEOUT_MS = 60_000

function baseUrl() {
  return (process.env.SEARCH_GATEWAY_URL || DEFAULT_BASE).replace(/\/$/, "")
}

async function postJson(path, body, abort) {
  const ctrl = new AbortController()
  const onAbort = () => ctrl.abort()
  if (abort) {
    if (abort.aborted) ctrl.abort()
    else abort.addEventListener("abort", onAbort, { once: true })
  }
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
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

function reputationLabel(score) {
  if (score == null || score < 0) return "Unknown"
  if (score >= 7) return "High"
  if (score >= 4) return "Medium"
  return "Low"
}

/** Official MCP formatSearchResults shape. */
function formatResolve(data) {
  const results = Array.isArray(data?.results) ? data.results : []
  if (!results.length) {
    return data?.error || "No libraries found matching the provided name."
  }
  const blocks = results.map((hit) => {
    const lines = [
      `- Title: ${hit.title || ""}`,
      `- Context7-compatible library ID: ${hit.id || ""}`,
      `- Description: ${hit.description || ""}`,
    ]
    if (hit.total_snippets != null && hit.total_snippets >= 0) {
      lines.push(`- Code Snippets: ${hit.total_snippets}`)
    }
    lines.push(`- Source Reputation: ${reputationLabel(hit.trust_score)}`)
    if (hit.benchmark_score != null && hit.benchmark_score > 0) {
      lines.push(`- Benchmark Score: ${hit.benchmark_score}`)
    }
    if (Array.isArray(hit.versions) && hit.versions.length) {
      lines.push(`- Versions: ${hit.versions.join(", ")}`)
    }
    return lines.join("\n")
  })
  return `Available Libraries:\n\n${blocks.join("\n----------\n")}`
}

export default async () => {
  return {
    tool: {
      // Official MCP: resolve-library-id
      "resolve-library-id": tool({
        description: [
          "Resolve a programming library/package/framework name to a Context7-compatible library ID (format /org/project or /org/project/version).",
          "Use whenever you need up-to-date library docs or code examples and do not already have a Context7 ID.",
          "Typical flow: resolve-library-id → pick the best ID from the list → query-docs with that ID.",
          "Skip this step only if the user (or prior context) already gave an ID like /vercel/next.js or /vercel/next.js/v14.3.0.",
          "Each result includes title, ID, description, snippet count, source reputation, benchmark score, and versions when available.",
          "Pick by name match, description fit, documentation coverage, and reputation. Do not call more than 3 times per user question.",
          "libraryName should use official punctuation (Next.js, not nextjs). query should state the user task so ranking is relevant. Never put secrets in query.",
        ].join(" "),
        args: {
          libraryName: tool.schema
            .string()
            .describe(
              "Official product/package name with proper punctuation (e.g. 'Next.js', 'React', 'Prisma')",
            ),
          query: tool.schema
            .string()
            .describe(
              "User task or question used to rank libraries (e.g. 'App Router middleware auth'). No secrets.",
            ),
        },
        async execute(args, ctx) {
          const libraryName = String(args.libraryName || "").trim()
          const query = String(args.query || "").trim()
          if (!libraryName) throw new Error("libraryName is required")
          if (!query) throw new Error("query is required")

          const data = await postJson(
            "/docs/search",
            { library_name: libraryName, query },
            ctx.abort,
          )
          return {
            title: libraryName,
            output: formatResolve(data),
            metadata: {
              libraryName,
              count: Array.isArray(data?.results) ? data.results.length : 0,
            },
          }
        },
      }),

      // Official MCP: query-docs
      "query-docs": tool({
        description: [
          "Retrieve current, version-aware documentation and code examples for a library from Context7.",
          "Use when writing or debugging against a specific library/SDK/framework API and you need accurate syntax, setup steps, or examples (training data may be stale).",
          "Requires an exact Context7 library ID from resolve-library-id, or one the user already provided (/org/project or /org/project/version).",
          "Scope each call to a single concept. Good: 'JWT session auth in middleware'. Bad vague: 'auth'. Bad multi-topic: 'routing and auth and caching'.",
          "For several distinct topics, call again with separate queries rather than one overloaded query.",
          "Do not call more than 3 times per user question. Never put API keys, passwords, or private code into query.",
        ].join(" "),
        args: {
          libraryId: tool.schema
            .string()
            .describe(
              "Exact Context7 ID, e.g. '/vercel/next.js' or '/vercel/next.js/v14.3.0'",
            ),
          query: tool.schema
            .string()
            .describe(
              "One focused docs question or task for that library. No secrets.",
            ),
        },
        async execute(args, ctx) {
          const libraryId = String(args.libraryId || "").trim()
          const query = String(args.query || "").trim()
          if (!libraryId) throw new Error("libraryId is required")
          if (!query) throw new Error("query is required")

          const data = await postJson(
            "/docs/context",
            { library_id: libraryId, query },
            ctx.abort,
          )
          const content = String(data?.content || "").trim()
          return {
            title: libraryId,
            output: content || "No documentation found for this library ID.",
            metadata: {
              libraryId: data?.library_id || libraryId,
            },
          }
        },
      }),
    },
  }
}
