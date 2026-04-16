"""CLI — command line interface for Search Gateway."""

import asyncio
import os
import sys
from pathlib import Path

import click

from ._utils import ensure_gateway_running


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Search Gateway — unified search with failover."""
    pass


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    help="Log level",
)
@click.option("--log-file", default=None, help="Log file path (default: console only)")
@click.option("--daemon", "-d", is_flag=True, help="Run in background (daemon mode)")
def start(port: int, config: str | None, log_level: str, log_file: str | None, daemon: bool):
    """Start the gateway server."""
    import warnings

    os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"
    warnings.filterwarnings("ignore")

    # If daemon mode, start in background
    if daemon:
        import subprocess
        from pathlib import Path

        # Default log file for daemon mode
        if not log_file:
            log_dir = Path.home() / ".sg" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = str(log_dir / "gateway.log")

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "sg.cli",
            "start",
            "--port",
            str(port),
            "--log-level",
            log_level,
            "--log-file",
            log_file,
        ]
        if config:
            cmd.extend(["--config", config])

        # Start in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        click.echo(f"Starting Search Gateway in background (PID: {process.pid})...")
        click.echo(f"Port: {port}")
        click.echo(f"Log file: {log_file}")

        # Wait a bit to check if it started successfully
        import time

        time.sleep(2)

        import httpx

        try:
            resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=30.0)
            if resp.status_code == 200:
                click.echo("\n✓ Gateway started successfully!")
                click.echo(f"\n  HTTP API:  http://127.0.0.1:{port}")
                click.echo(f"  Web UI:    http://127.0.0.1:{port}")
                click.echo("\n  Commands:  search-gateway status | search-gateway stop | search-gateway web")
                click.echo(f"  Logs:      tail -f {log_file}\n")
            else:
                click.echo(
                    f"\n⚠ Gateway may not have started correctly. Check logs: {log_file}", err=True
                )
        except Exception:
            click.echo(
                f"\n⚠ Gateway may not have started correctly. Check logs: {log_file}", err=True
            )

        return

    # Setup logging
    from ._logging import setup_logging

    setup_logging(log_level=log_level, log_file=log_file)

    click.echo(f"Starting Search Gateway on port {port}...")
    if log_file:
        click.echo(f"Logging to: {log_file}")
    click.echo(f"Log level: {log_level}")

    async def run():
        from .server.gateway import Gateway

        gateway = Gateway(config_path=config, port=port)
        await gateway.start()
        click.echo(f"\n  HTTP API:  http://127.0.0.1:{port}")
        click.echo(f"  Web UI:    http://127.0.0.1:{port}")
        click.echo("\n  Commands:  search-gateway search 'query' | search-gateway status | search-gateway stop\n")
        await gateway.wait_shutdown()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        click.echo("\nGateway stopped.")


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def mcp(port: int, config: str | None):
    """Start MCP server in stdio mode (for Claude Desktop).

    Connects to a running gateway daemon (starts one if needed) and exposes
    MCP tools for LLM integration.
    """
    import warnings

    warnings.filterwarnings("ignore")

    async def run():
        from .server.mcp_server import MCPServer

        server = MCPServer(port=port, config=config)
        await server.run_stdio()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
def stop(port: int):
    """Stop the gateway server."""
    import httpx

    try:
        httpx.post(f"http://127.0.0.1:{port}/shutdown", timeout=5.0)
        click.echo("Gateway stopped.")
    except Exception as e:
        click.echo(f"Failed to stop gateway: {e}", err=True)


def _print_result_file(data: dict) -> None:
    """Print result as TOON format for LLM consumption."""
    query = data.get("query", "")
    result_file = data.get("result_file", "")
    results = data.get("results", [])
    total = data.get("total", 0)

    click.echo(f"query: {query}")
    if result_file:
        click.echo(f"Hint: 详细结果存到了 {result_file}，请务必读取该文件获取完整的搜索结果！")
    click.echo("")

    preview_count = min(len(results), 5)
    click.echo(f"results[{preview_count}]{{line,title,url,score}}:")
    for i, r in enumerate(results[:preview_count], 1):
        score = r.get("score", 0)
        score_str = f"{score:.2f}" if score else "-"
        title = r.get("title", "")[:50]
        if len(r.get("title", "")) > 50:
            title += "..."
        url = r.get("url", "")
        # line=i means read line i from the file
        click.echo(f"  {i},{title},{url},{score_str}")

    if total > preview_count:
        click.echo(f"  ... ({total - preview_count} more)")

    click.echo("")
    click.echo("To read specific results, read file lines:")
    click.echo("  Line 1 = result [1], Line 2 = result [2], etc.")


@cli.command()
@click.argument("queries", nargs=-1, required=True)
@click.option("--provider", "-p", default=None, help="Search provider")
@click.option("--max", "-n", default=10, help="Max results")
@click.option(
    "--include-domain", "include_domains", multiple=True, help="Restrict search to a domain"
)
@click.option(
    "--exclude-domain", "exclude_domains", multiple=True, help="Exclude a domain from search"
)
@click.option("--time-range", type=click.Choice(["day", "week", "month", "year"]), default=None)
@click.option(
    "--search-depth",
    type=click.Choice(["basic", "advanced", "fast", "ultra-fast"]),
    default="basic",
)
@click.option(
    "--extra", "-e", default=None, help='Extra params as JSON (e.g. \'{"location":"CN"}\')'
)
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def search(
    queries: tuple[str, ...],
    provider: str | None,
    max: int,
    include_domains: tuple[str, ...],
    exclude_domains: tuple[str, ...],
    time_range: str | None,
    search_depth: str,
    extra: str | None,
    port: int,
    config: str | None,
):
    """Execute one or more search queries. Prints result file path(s)."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)

    import json

    extra_dict = {}
    if extra:
        try:
            extra_dict = json.loads(extra)
        except json.JSONDecodeError:
            click.echo(f"Error: Invalid JSON in --extra: {extra}", err=True)
            sys.exit(1)

    payload = {
        "provider": provider,
        "max_results": max,
        "include_domains": list(include_domains),
        "exclude_domains": list(exclude_domains),
        "time_range": time_range,
        "search_depth": search_depth,
        "extra": extra_dict,
    }

    try:
        if len(queries) == 1:
            resp = httpx.post(
                f"http://127.0.0.1:{port}/search",
                json={"query": queries[0], **payload},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            _print_result_file(data)
        else:
            resp = httpx.post(
                f"http://127.0.0.1:{port}/search/batch",
                json={"queries": list(queries), **payload},
                timeout=60.0,
            )
            resp.raise_for_status()
            for data in resp.json():
                _print_result_file(data)

    except httpx.ConnectError:
        click.echo("Error: Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("urls", nargs=-1, required=True)
@click.option("--provider", "-p", default=None, help="Extract provider")
@click.option("--format", "-f", default="markdown", type=click.Choice(["markdown", "text"]))
@click.option(
    "--extra", "-e", default=None, help='Extra params as JSON (e.g. \'{"device":"mobile"}\')'
)
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def extract(
    urls: tuple[str],
    provider: str | None,
    format: str,
    extra: str | None,
    port: int,
    config: str | None,
):
    """Extract content from URLs."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)
    try:
        import json

        extra_dict = {}
        if extra:
            try:
                extra_dict = json.loads(extra)
            except json.JSONDecodeError:
                click.echo(f"Error: Invalid JSON in --extra: {extra}", err=True)
                sys.exit(1)

        resp = httpx.post(
            f"http://127.0.0.1:{port}/extract",
            json={"urls": list(urls), "provider": provider, "format": format, "extra": extra_dict},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        result_files = data.get("result_files")
        if result_files:
            for f in result_files:
                if f.get("error"):
                    click.echo(f"error: {f['error']} | {f.get('url', '')}")
                else:
                    title = f.get("title") or ""
                    click.echo(
                        f"file:{f.get('file', '')} | {f.get('chars', 0)}c {f.get('lines', 0)}L | {title}"
                    )
                    click.echo(f"  {f.get('url', '')}")
        else:
            for r in data.get("results", []):
                if r.get("error"):
                    click.echo(f"error: {r['error']} | {r.get('url', '')}")
                else:
                    click.echo(f"URL: {r['url']}")
                    if r.get("title"):
                        click.echo(f"Title: {r['title']}")
                    length = len(r.get("content", ""))
                    click.echo(f"Status: Success ({length} chars)")

    except httpx.ConnectError:
        click.echo("Error: Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("topic")
@click.option("--depth", "-d", default="auto", type=click.Choice(["mini", "pro", "auto"]))
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def research(topic: str, depth: str, port: int, config: str | None):
    """Execute deep research on a topic."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)

    click.echo(f"Researching: {topic} (depth: {depth})...")

    try:
        resp = httpx.post(
            f"http://127.0.0.1:{port}/research",
            json={"topic": topic, "depth": depth},
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()
        result_file = data.get("result_file", "")
        
        if result_file:
            click.echo(f"Hint: 深度研究报告已存入 {result_file}，请读取该文件第 1 行获取完整 JSON 报告！")
        click.echo("")
        
        content = data.get("content", "")
        click.echo("Preview:")
        click.echo(content[:1000] + ("\n\n...(truncated)..." if len(content) > 1000 else ""))

    except httpx.ConnectError:
        click.echo("Error: Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def status(port: int, config: str | None):
    """Show gateway status."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        click.echo("\nSearch Gateway Status\n")
        click.echo(f"  Running:   {data['running']}")
        click.echo(f"  Port:      {data['port']}")
        click.echo(f"  Strategy:  {data.get('strategy', 'N/A')}")
        click.echo(f"  Providers: {len(data['providers']['available'])} available")
        click.echo(f"  Available: {', '.join(data['providers']['available'])}")

        if data.get("metrics"):
            click.echo("\n  Metrics:")
            for name, m in data["metrics"].items():
                cb = (
                    f" [{m.get('circuit_breaker', 'closed')}]"
                    if m.get("circuit_breaker") != "closed"
                    else ""
                )
                extra = ""
                if m.get("disabled_seconds_remaining"):
                    extra = f", retry in {m['disabled_seconds_remaining']}s"
                if m.get("last_failure_type") and m.get("last_failure_type") != "transient":
                    extra += f", reason={m['last_failure_type']}"
                click.echo(
                    f"    {name}: {m['successes']}/{m['requests']} success, "
                    f"{m['avg_latency_ms']:.0f}ms avg{cb}{extra}"
                )

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def providers(port: int, config: str | None):
    """List available providers."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/providers", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        click.echo("\nAvailable Providers\n")
        for p in data:
            status_icon = "+" if p.get("circuit_breaker", "closed") != "open" else "-"
            fallback = (
                f" (fallback: {','.join(p['fallback_for'])})" if p.get("fallback_for") else ""
            )
            ptype = f" [{p.get('type', '')}]" if p.get("type") else ""
            cb = (
                f" [circuit: {p['circuit_breaker']}]"
                if p.get("circuit_breaker") != "closed"
                else ""
            )
            click.echo(f"  {status_icon} {p['name']}{ptype}{fallback}{cb}")
            click.echo(f"      Capabilities: {', '.join(p['capabilities'])}")
            if p.get("search_features"):
                click.echo(f"      Search params: {', '.join(p['search_features'])}")
            click.echo(f"      Priority: {p['priority']}")
            if p.get("disabled_seconds_remaining"):
                click.echo(f"      Retry in: {p['disabled_seconds_remaining']}s")
            if p.get("last_failure_type") and p.get("last_failure_type") != "transient":
                click.echo(f"      Last failure: {p['last_failure_type']}")
            click.echo()

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
def health(port: int):
    """Run health check on all providers."""
    import httpx

    try:
        resp = httpx.post(f"http://127.0.0.1:{port}/health-check", timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

        click.echo("\nHealth Check Results\n")
        click.echo(f"  Healthy:   {', '.join(data['healthy']) or 'None'}")
        unhealthy_names = [
            u["name"] if isinstance(u, dict) else u for u in data.get("unhealthy", [])
        ]
        click.echo(f"  Unhealthy: {', '.join(unhealthy_names) or 'None'}")

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)


@cli.command()
@click.argument("entry_id", required=False, default=None)
@click.option("--clear", is_flag=True, help="Clear all history")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.option("--port", default=8100, help="Gateway port")
def history(entry_id: str | None, clear: bool, limit: int, port: int):
    """Show search history."""
    import httpx

    try:
        if clear:
            resp = httpx.delete(f"http://127.0.0.1:{port}/api/history", timeout=5.0)
            resp.raise_for_status()
            click.echo(f"Cleared {resp.json()['deleted']} entries.")
            return

        if entry_id:
            resp = httpx.get(f"http://127.0.0.1:{port}/api/history/{entry_id}", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            click.echo(f"\nQuery:    {data['query']}")
            click.echo(f"Provider: {data['provider']}")
            click.echo(f"Time:     {data['timestamp']}")
            click.echo(f"Results:  {data['total']} ({data['latency_ms']:.0f}ms)\n")
            if data.get("results"):
                for i, r in enumerate(data["results"], 1):
                    click.echo(f"  [{i}] {r['title']}")
                    click.echo(f"      {r['url']}")
                    if r.get("content"):
                        click.echo(f"      {r['content'][:150]}...")
                    click.echo()
            return

        resp = httpx.get(
            f"http://127.0.0.1:{port}/api/history",
            params={"limit": limit},
            timeout=5.0,
        )
        resp.raise_for_status()
        entries = resp.json()

        if not entries:
            click.echo("No search history.")
            return

        click.echo(f"\nRecent Searches ({len(entries)})\n")
        for e in entries:
            ts = e["timestamp"][:19].replace("T", " ")
            click.echo(f"  {ts}  [{e['provider']}]  {e['query']}  ({e['total']} results)")
        click.echo("\nUse 'search-gateway history <id>' to see full results.")

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'search-gateway start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def init(config: str | None):
    """Initialize Search Gateway configuration."""
    from .models.config import resolve_config_path

    config_path = resolve_config_path(config)

    if config_path.exists():
        click.echo(f"Config already exists: {config_path}")
        if not click.confirm("Overwrite?"):
            return

    # Create default config template
    template = {
        "server": {"port": 8100},
        "providers": {
            "duckduckgo": {
                "type": "duckduckgo",
                "enabled": True,
                "priority": 100,
                "fallback_for": ["search"],
            }
        },
    }

    # Save config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    with open(config_path, "w") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
        f.write("\n")

    click.echo(f"\n✓ Created config: {config_path}")
    click.echo("\nDefault provider: DuckDuckGo (free, no API key required)")
    click.echo("\nTo add more providers, edit the config file or use the Web UI:")
    click.echo("  search-gateway start && search-gateway web")
    click.echo("\nAvailable providers:")
    click.echo("  - Tavily (search, extract, research) - requires API key")
    click.echo("  - Exa (search, extract) - requires API key")
    click.echo("  - Brave (search) - requires API key")
    click.echo("  - You.com (search, extract) - requires API key")
    click.echo("  - Firecrawl (extract) - requires API key")
    click.echo("  - Jina (extract) - free, no API key")
    click.echo("  - SearXNG (search) - requires self-hosted instance")
    click.echo("\nTest your setup:")
    click.echo("  search-gateway search 'test query'")


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
def web(port: int):
    """Open Web UI in browser."""
    import webbrowser

    url = f"http://127.0.0.1:{port}"
    click.echo(f"Opening {url} ...")
    webbrowser.open(url)


@cli.command()
@click.option("--copy", is_flag=True, help="Copy prompt to clipboard")
def setup(copy: bool):
    """Output setup prompt for AI coding assistants."""
    prompt_path = _find_prompt("setup.md")
    if not prompt_path:
        click.echo("Error: setup.md not found", err=True)
        sys.exit(1)

    prompt = prompt_path.read_text()
    if copy:
        import subprocess

        try:
            subprocess.run(["pbcopy"], input=prompt.encode(), check=True)
            click.echo("Prompt copied to clipboard. Paste it to your AI agent to start setup.")
        except FileNotFoundError:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=prompt.encode(),
                    check=True,
                )
                click.echo("Prompt copied to clipboard. Paste it to your AI agent to start setup.")
            except FileNotFoundError:
                click.echo("Error: no clipboard tool found (pbcopy/xclip)", err=True)
                click.echo("Use 'search-gateway setup' without --copy to print the prompt.", err=True)
                sys.exit(1)
    else:
        click.echo(prompt)


def _find_prompt(name: str) -> Path | None:
    """Find a prompt file in dev or installed location."""
    # Development mode: relative to source
    dev_path = Path(__file__).parent.parent.parent / "prompts" / name
    if dev_path.exists():
        return dev_path

    # Installed mode: in share directory
    if sys.prefix:
        installed_path = Path(sys.prefix) / "share" / "search-gateway" / "prompts" / name
        if installed_path.exists():
            return installed_path

    return None


_SKILL_MD = """---
name: search-gateway
description: >
  Use when the user needs web search, latest information, webpage content extraction, or deep research.
  Triggers on "搜索一下", "查一下", "最新", "提取网页", "深度研究", "search for", "look up", "extract URL".
---

# Search Gateway

## 执行检查点

- [ ] 结果包含 `file:` 路径时，**必须读取该文件**获取完整内容
- [ ] 不要主动指定 `-p provider`，让自动故障转移工作
- [ ] 如果命令报错网关未启动，重试一次（CLI 会自动后台启动）

## 核心命令

| 场景 | 命令 |
|------|------|
| 搜索 | `search-gateway search "query"` |
| 批量搜索 | `search-gateway search "q1" "q2" "q3"` |
| 限制结果数 | `search-gateway search "query" -n 10` |
| 按时间过滤 | `search-gateway search "query" --time-range week` |
| 限定域名 | `search-gateway search "query" --include-domain github.com` |
| 排除域名 | `search-gateway search "query" --exclude-domain medium.com` |
| 提取网页 | `search-gateway extract "https://example.com"` |
| 深度研究 | `search-gateway research "topic"` |
| 更深入研究 | `search-gateway research "topic" -d pro` |
| 查看状态 | `search-gateway status` |

## Known Gotchas

- **不读文件 = 丢失结果**：`search-gateway search` 和 `research` 的完整结果通常在返回的文件路径中，stdout 只是预览。看到 `file:` 必须执行 ReadFile 读取。
- **不要手动指定 provider**：自动路由已配置多 provider 故障转移，手动 `-p tavily` 等会绕过最优选择。仅在用户明确要求某 provider 时才用 `-p`。
- **网关未启动时自动启动**：首次调用可能因后台启动而稍慢，如果收到 "Gateway not running"，等待 3-5 秒后重试即可。
- **extract 结果也要读文件**：`search-gateway extract` 同样返回文件路径，必须读取文件获取提取内容。

## MCP 集成（可选）

如果当前 AI 工具支持 MCP，可配置原生工具调用：
- Claude Code: `claude mcp add search-gateway stdio search-gateway mcp`
"""


@cli.group()
def skill():
    """Manage AI coding assistant skills."""
    pass


@skill.command(name="install")
@click.option(
    "--path",
    "-p",
    default=None,
    help="Skills root directory (default: ~/.agents/skills)",
)
def skill_install(path: str | None):
    """Install Search Gateway skill for AI assistants."""
    skills_dir = Path(path).expanduser() if path else Path.home() / ".agents" / "skills"
    target = skills_dir / "search-gateway"

    if not click.confirm(f"Install skill to {target}?"):
        click.echo("Cancelled.")
        return

    target.mkdir(parents=True, exist_ok=True)
    skill_file = target / "SKILL.md"
    skill_file.write_text(_SKILL_MD, encoding="utf-8")

    click.echo(f"\n✓ Skill installed: {skill_file}")
    click.echo("\nSupported AI tools will now automatically use search-gateway for web search.")
    click.echo("\nTip: Restart your AI coding assistant to load the new skill.")


if __name__ == "__main__":
    cli()
