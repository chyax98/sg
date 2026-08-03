"""CLI — command line interface for Search Gateway."""

import asyncio
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import click
import httpx

from ._agent_output import format_extract_output, format_research_output, format_search_output
from ._utils import ensure_gateway_running


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Search Gateway — unified search with failover.

    \b
    使用指南：
      search-gateway skill get             打印 SKILL.md 原文到 stdout（AI 助手视角）
      search-gateway setup                 输出 AI 配置向导 prompt（交互式引导）
      search-gateway plugin install        装 opencode 插件到 ~/.config/opencode/plugins/
      search-gateway plugin setup          把 plugin 引用写入 opencode.json（idempotent）
      search-gateway init                  初始化 ~/.sg/config.json

    \b
    完整文档：https://github.com/chyax98/sg
    安装方案：docs/install/{uv,source,macos-daemon}.md
    """
    pass


def _ensure_gateway_or_exit(port: int, config: str | None = None) -> None:
    try:
        ensure_gateway_running(port, config)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _extract_http_error_detail(error: httpx.HTTPStatusError) -> str:
    try:
        payload = error.response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict) and payload.get("detail"):
        return str(payload["detail"])

    text = error.response.text.strip()
    if text:
        return text

    return f"HTTP {error.response.status_code}"


def _exit_for_request_error(error: Exception) -> None:
    if isinstance(error, httpx.ConnectError):
        click.echo("Error: Gateway not running. Start with 'search-gateway start'", err=True)
    elif isinstance(error, httpx.HTTPStatusError):
        click.echo(f"Error: {_extract_http_error_detail(error)}", err=True)
    elif isinstance(error, httpx.HTTPError):
        click.echo(f"Error: {error}", err=True)
    else:
        click.echo(f"Error: {error}", err=True)
    sys.exit(1)


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
                click.echo(f"  MCP HTTP:  http://127.0.0.1:{port}/mcp")
                click.echo(f"  Web UI:    http://127.0.0.1:{port}")
                click.echo(
                    "\n  Commands:  search-gateway status | search-gateway stop | search-gateway web"
                )
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
        click.echo(f"  MCP HTTP:  http://127.0.0.1:{port}/mcp")
        click.echo(f"  Web UI:    http://127.0.0.1:{port}")
        click.echo(
            "\n  Commands:  search-gateway search 'query' | search-gateway status | search-gateway stop\n"
        )
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
    try:
        httpx.post(f"http://127.0.0.1:{port}/shutdown", timeout=5.0).raise_for_status()
        click.echo("Gateway stopped.")
    except Exception as e:
        _exit_for_request_error(e)


def _print_result_file(data: dict) -> None:
    """Print result as TOON format for LLM consumption."""
    click.echo(format_search_output(data))


@cli.command()
@click.argument("queries", nargs=-1, required=True)
@click.option("--provider", "-p", default=None, help="Search provider")
@click.option("--max", "-n", default=10, help="Max results")
@click.option("--include-domain", "domains", multiple=True, help="Restrict search to a domain")
@click.option(
    "--exclude-domain", "exclude_domains", multiple=True, help="Exclude a domain from search"
)
@click.option("--time-range", type=click.Choice(["day", "week", "month", "year"]), default=None)
@click.option(
    "--search-depth",
    type=click.Choice(["basic", "advanced", "fast", "ultra-fast"]),
    default="basic",
)
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def search(
    queries: tuple[str, ...],
    provider: str | None,
    max: int,
    domains: tuple[str, ...],
    exclude_domains: tuple[str, ...],
    time_range: str | None,
    depth: str,
    port: int,
    config: str | None,
):
    """Execute one or more search queries. Prints result file path(s)."""
    # Ensure gateway is running, start if needed
    _ensure_gateway_or_exit(port, config)

    payload = {
        "provider": provider,
        "limit": max,
        "domains": list(domains),
        "exclude_domains": list(exclude_domains),
        "time_range": time_range,
        "depth": depth,
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

    except Exception as e:
        _exit_for_request_error(e)


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
    # Ensure gateway is running, start if needed
    _ensure_gateway_or_exit(port, config)
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
        click.echo(format_extract_output(data))

    except Exception as e:
        _exit_for_request_error(e)


@cli.command()
@click.argument("topic")
@click.option("--depth", "-d", default="auto", type=click.Choice(["mini", "pro", "auto"]))
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def research(topic: str, depth: str, port: int, config: str | None):
    """Execute deep research on a topic."""
    # Ensure gateway is running, start if needed
    _ensure_gateway_or_exit(port, config)

    try:
        resp = httpx.post(
            f"http://127.0.0.1:{port}/research",
            json={"topic": topic, "depth": depth},
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()
        click.echo(format_research_output(data))

    except Exception as e:
        _exit_for_request_error(e)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def status(port: int, config: str | None):
    """Show gateway status."""
    # Ensure gateway is running, start if needed
    _ensure_gateway_or_exit(port, config)
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

    except Exception as e:
        _exit_for_request_error(e)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def providers(port: int, config: str | None):
    """List available providers."""
    # Ensure gateway is running, start if needed
    _ensure_gateway_or_exit(port, config)
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

    except Exception as e:
        _exit_for_request_error(e)


@cli.command()
@click.option("--port", default=8100, help="Gateway port")
def health(port: int):
    """Run health check on all providers."""
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

    except Exception as e:
        _exit_for_request_error(e)


@cli.command()
@click.argument("entry_id", required=False, default=None)
@click.option("--clear", is_flag=True, help="Clear all history")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.option("--port", default=8100, help="Gateway port")
def history(entry_id: str | None, clear: bool, limit: int, port: int):
    """Show search history."""
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
            elif data.get("content"):
                click.echo(data["content"])
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

    except Exception as e:
        _exit_for_request_error(e)


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
                click.echo(
                    "Use 'search-gateway setup' without --copy to print the prompt.", err=True
                )
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

本机装了 search-gateway，遇到搜索/提取/研究需求**优先**用它（聚合多引擎、自动故障转移、本地无限制）。

## 先决条件

- `search-gateway status` 显示 running；没跑就 `search-gateway start --daemon`
- 首次使用：`search-gateway init` 创建 `~/.sg/config.json`（不配 key 默认用 DuckDuckGo）

## 核心命令（CLI 直接用）

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

## 集成到 AI 工具（按场景选一种）

| 场景 | 命令 / 配置 |
|---|---|
| OpenCode 原生 plugin（websearch / webfetch / context7） | `search-gateway plugin install && search-gateway plugin setup` |
| OpenCode remote MCP | `opencode.json` 的 `mcp` 段加 `http://127.0.0.1:8100/mcp`（`type: remote`, `oauth: false`） |
| Claude Code MCP | `claude mcp add search-gateway stdio search-gateway mcp` |
| Codex / Kimi（TOML） | `[mcp_servers.search-gateway]` `command = "search-gateway"` `args = ["mcp"]` |
| Gemini CLI（JSON） | `~/.gemini/settings.json` 的 `mcpServers.search-gateway` |
| HTTP API（任意语言） | `search-gateway start` 后 POST `http://127.0.0.1:8100/{search,extract,research}` |
| Python SDK | `from sg.sdk import SearchClient` |

## macOS daemon 自启（可选）

让 sg 开机自启、崩溃拉起，OpenCode plugin / MCP 常驻依赖建议配：

- 仓库内：`make install-launchd`
- 详细步骤：`docs/install/macos-daemon.md`

## AI 引导式配置（可选）

`search-gateway setup` 输出交互式配置向导 prompt（带用户配 provider API key、选集成方式）。

## Known Gotchas

- **结果已内联**：`search` / `extract` / `research` 的正文在 stdout 里，**直接用输出作答**，不要再读历史文件。
- **不要手动指定 provider**：自动路由已配多 provider 故障转移，手动 `-p tavily` 会绕过最优选择。仅在用户明确要求某 provider 时才用 `-p`。
- **网关未启动时自动启动**：首次调用可能因后台启动稍慢，若收到 "Gateway not running"，等 3-5 秒重试。
- **搜完别乱 extract**：用 search 的 snippet 答题；只有用户明确要整页正文时才 `extract` 给定 URL。

## 更多

- 完整文档：https://github.com/chyax98/sg
- 安装方案：`docs/install/{uv,source,macos-daemon}.md`
- 集成方案对比：README.md "集成方案对比" 段
"""


@cli.group()
def skill():
    """Manage AI coding assistant skills."""
    pass


@cli.group()
def plugin():
    """Manage opencode/IDE plugins."""
    pass


@plugin.command(name="install")
@click.option(
    "--path",
    "-p",
    default=None,
    help="Plugins directory (default: ~/.config/opencode/plugins)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing files")
def plugin_install(path: str | None, force: bool):
    """Install OpenCode plugins (websearch/webfetch/context7) to local opencode."""
    plugins_dir = (
        Path(path).expanduser() if path else Path.home() / ".config" / "opencode" / "plugins"
    )
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # Wheel: sg/_plugins_data/; dev/editable: <repo>/plugins/opencode/
    src_candidates = [
        Path(__file__).resolve().parent / "_plugins_data",
        Path(__file__).resolve().parent.parent.parent / "plugins" / "opencode",
    ]
    src_dir = next((p for p in src_candidates if p.is_dir()), None)
    if not src_dir:
        click.echo(f"Error: plugin sources not found (tried {src_candidates})", err=True)
        sys.exit(1)

    targets = ["search-gateway-web.js", "search-gateway-context7.js"]
    installed: list[Path] = []
    skipped: list[Path] = []
    for name in targets:
        src = src_dir / name
        if not src.is_file():
            click.echo(f"Error: missing plugin source {name}", err=True)
            sys.exit(1)
        dst = plugins_dir / name
        if dst.exists() and not force:
            skipped.append(dst)
            continue
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        installed.append(dst)

    click.echo(f"\n✓ Installed {len(installed)} plugin(s) to {plugins_dir}:")
    for p in installed:
        click.echo(f"  - {p.name}")
    if skipped:
        click.echo("\nSkipped (already exist, use --force to overwrite):")
        for p in skipped:
            click.echo(f"  - {p.name}")

    click.echo("\nNext: add to opencode.json plugin array, then restart opencode.")


@skill.command(name="get")
@click.argument("name", required=False, default="search-gateway")
def skill_get(name: str):
    """Print SKILL.md content to stdout.

    SKILL 内容打包在包内；AI 助手运行时直接调用读取 stdout。
    """
    available = {"search-gateway": _SKILL_MD}
    content = available.get(name)
    if content is None:
        click.echo(
            f"Error: unknown skill '{name}'. Available: {', '.join(sorted(available))}",
            err=True,
        )
        sys.exit(1)
    click.echo(content, nl=False)


@plugin.command(name="setup")
@click.option(
    "--config",
    "-c",
    default=None,
    help="opencode.json path (default: ~/.config/opencode/opencode.json)",
)
def plugin_setup(config: str | None):
    """Add Search Gateway plugin entries to opencode.json (idempotent)."""
    import json

    config_path = (
        Path(config).expanduser()
        if config
        else Path.home() / ".config" / "opencode" / "opencode.json"
    )
    if not config_path.is_file():
        click.echo(f"Error: {config_path} not found", err=True)
        sys.exit(1)

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        click.echo(f"Error: invalid JSON in {config_path}: {e}", err=True)
        sys.exit(1)

    existing = data.get("plugin", [])
    if not isinstance(existing, list):
        click.echo("Error: 'plugin' field is not a list in opencode.json", err=True)
        sys.exit(1)

    plugins_dir = Path.home() / ".config" / "opencode" / "plugins"
    targets = [
        str(plugins_dir / "search-gateway-web.js"),
        str(plugins_dir / "search-gateway-context7.js"),
    ]

    def _entry_path(entry: object) -> str | None:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, list) and entry:
            first = entry[0]
            return first if isinstance(first, str) else None
        return None

    existing_paths = {_entry_path(e) for e in existing}
    added = [t for t in targets if t not in existing_paths]

    if not added:
        click.echo(f"✓ All Search Gateway plugins already referenced in {config_path}")
        return

    data["plugin"] = [*existing, *added]
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    click.echo(f"✓ Added {len(added)} plugin(s) to {config_path}:")
    for p in added:
        click.echo(f"  - {Path(p).name}")
    click.echo("\nRestart opencode to load the plugins.")


# ============================================================
# daemon group: macOS launchd 自启 / Linux & Windows 占位
# ============================================================

_DAEMON_LABEL = "com.search-gateway"
_PLIST_PRINT_KEYS = ("state", "pid", "last exit code", "path =")
_PLIST_DEFAULT_PORT = 8100


def _gen_plist(bin_path: str, home: str, port: int) -> str:
    """Generate launchd plist content with runtime paths (no hardcoded usernames)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_DAEMON_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{bin_path}</string>
        <string>start</string>
        <string>--port</string>
        <string>{port}</string>
        <string>--log-level</string>
        <string>INFO</string>
        <string>--log-file</string>
        <string>{home}/.sg/logs/gateway.log</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{home}/.sg</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>{home}/.sg/logs/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{home}/.sg/logs/launchd-stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>{home}</string>
        <key>PYTHONWARNINGS</key>
        <string>ignore::DeprecationWarning</string>
    </dict>
</dict>
</plist>
"""


def _lc(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run launchctl / shell command, capture output, never raise."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _bootout(label: str) -> None:
    uid = os.getuid()
    _lc(["launchctl", "bootout", f"gui/{uid}/{label}"])


def _bootstrap(plist_path: Path) -> subprocess.CompletedProcess:
    uid = os.getuid()
    return _lc(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)])


def _enable(label: str) -> None:
    uid = os.getuid()
    _lc(["launchctl", "enable", f"gui/{uid}/{label}"])


def _http_status_ok(port: int = _PLIST_DEFAULT_PORT) -> bool:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/status", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _require_macos(action: str) -> None:
    if platform.system() != "Darwin":
        click.echo(
            f"Error: daemon {action} on {platform.system()} not yet supported. "
            f"Run 'search-gateway start --daemon' manually instead.",
            err=True,
        )
        sys.exit(1)


@cli.group()
def daemon():
    """Manage daemon auto-start (macOS launchd; Linux/Windows TBD)."""
    pass


@daemon.command(name="install")
@click.option("--port", "-p", default=_PLIST_DEFAULT_PORT, help="Gateway port")
@click.option("--force", "-f", is_flag=True, help="Reinstall even if already installed")
def daemon_install(port: int, force: bool):
    """Install daemon auto-start (macOS: launchd)."""
    _require_macos("install")

    bin_path = shutil.which("search-gateway")
    if not bin_path:
        click.echo("Error: search-gateway not found in PATH", err=True)
        sys.exit(1)

    home = Path.home()
    agents_dir = home / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (home / ".sg" / "logs").mkdir(parents=True, exist_ok=True)

    plist_path = agents_dir / f"{_DAEMON_LABEL}.plist"

    # Idempotent: 已装且未要求 force 就跳过
    if plist_path.exists() and not force:
        click.echo(f"✓ Already installed at {plist_path}")
        click.echo("  Use --force to reinstall, or 'daemon uninstall' first.")
        return

    # 若已装，先 bootout 旧实例
    if plist_path.exists():
        _bootout(_DAEMON_LABEL)

    # 停掉非 launchd 托管的旧 daemon，避免端口冲突
    _lc(["search-gateway", "stop"])
    time.sleep(1)

    # 生成并写 plist
    plist_path.write_text(_gen_plist(bin_path, str(home), port), encoding="utf-8")

    # bootstrap + enable
    r = _bootstrap(plist_path)
    if r.returncode != 0:
        click.echo(f"Error: launchctl bootstrap failed: {r.stderr.strip()}", err=True)
        sys.exit(1)
    _enable(_DAEMON_LABEL)

    # 验证
    time.sleep(2)
    if _http_status_ok(port):
        click.echo(f"✓ Daemon installed and running at http://127.0.0.1:{port}")
        click.echo(f"  plist: {plist_path}")
        click.echo(f"  logs:  {home}/.sg/logs/launchd-{{stdout,stderr}}.log")
    else:
        click.echo(
            "⚠ Daemon plist installed but /status not responding. Check:\n"
            f"  tail -20 {home}/.sg/logs/launchd-stderr.log",
            err=True,
        )
        sys.exit(1)


@daemon.command(name="uninstall")
def daemon_uninstall():
    """Uninstall daemon auto-start."""
    _require_macos("uninstall")

    home = Path.home()
    agents_dir = home / "Library" / "LaunchAgents"

    plist_path = agents_dir / f"{_DAEMON_LABEL}.plist"
    if plist_path.exists():
        _bootout(_DAEMON_LABEL)
        plist_path.unlink(missing_ok=True)
        click.echo(f"✓ Removed {_DAEMON_LABEL}")
    else:
        click.echo("Nothing to uninstall.")


@daemon.command(name="status")
def daemon_status():
    """Show daemon auto-start status."""
    _require_macos("status")

    home = Path.home()
    agents_dir = home / "Library" / "LaunchAgents"
    plist_path = agents_dir / f"{_DAEMON_LABEL}.plist"

    if not plist_path.exists():
        click.echo(f"Daemon auto-start NOT installed (expected {plist_path}).")
        click.echo("  Run 'search-gateway daemon install' to enable.")
        return

    uid = os.getuid()
    r = _lc(["launchctl", "print", f"gui/{uid}/{_DAEMON_LABEL}"])
    if r.returncode == 0:
        click.echo(f"Label:   {_DAEMON_LABEL}")
        for line in r.stdout.splitlines():
            stripped = line.strip()
            for key in _PLIST_PRINT_KEYS:
                if stripped.startswith(key):
                    click.echo(f"  {stripped}")
                    break
    else:
        click.echo(f"plist exists but label not loaded: {r.stderr.strip()}")

    if _http_status_ok():
        click.echo("HTTP /status: ✓ running")
    else:
        click.echo("HTTP /status: ✗ not responding")


if __name__ == "__main__":
    cli()
