"""CLI — command line interface for Search Gateway."""

import asyncio
import os
import sys
from pathlib import Path

import click

from ._utils import ensure_gateway_running


@click.group()
def cli():
    """Search Gateway — unified search with failover."""
    pass


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Log level")
@click.option("--log-file", default=None, help="Log file path (default: console only)")
def start(port: int, config: str | None, log_level: str, log_file: str | None):
    """Start the gateway server."""
    import warnings
    os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"
    warnings.filterwarnings("ignore")

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
        click.echo("\n  Commands:  sg search 'query' | sg status | sg stop\n")
        await gateway.wait_shutdown()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        click.echo("\nGateway stopped.")


@cli.command()
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def mcp(config: str | None):
    """Start MCP server in stdio mode (for Claude Desktop)."""
    import warnings
    warnings.filterwarnings("ignore")

    async def run():
        from .server.gateway import Gateway
        from .server.mcp_server import MCPServer

        gateway = Gateway(config_path=config)
        await gateway.providers.initialize()

        server = MCPServer(gateway)
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
    """Print result file info in concise format."""
    path = Path(data["result_file"])
    try:
        size_kb = path.stat().st_size / 1024
        click.echo(
            f'query="{data["query"]}" provider={data["provider"]} '
            f'results={data["total"]} size={size_kb:.1f}KB file={path}'
        )
    except OSError:
        click.echo(f'query="{data["query"]}" file={data["result_file"]} (unreadable)')


@cli.command()
@click.argument("queries", nargs=-1, required=True)
@click.option("--provider", "-p", default=None, help="Search provider")
@click.option("--max", "-n", default=10, help="Max results")
@click.option("--include-domain", "include_domains", multiple=True, help="Restrict search to a domain")
@click.option("--exclude-domain", "exclude_domains", multiple=True, help="Exclude a domain from search")
@click.option("--time-range", type=click.Choice(["day", "week", "month", "year"]), default=None)
@click.option("--search-depth", type=click.Choice(["basic", "advanced", "fast", "ultra-fast"]), default="basic")
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
    port: int,
    config: str | None,
):
    """Execute one or more search queries. Prints result file path(s)."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)

    payload = {
        "provider": provider,
        "max_results": max,
        "include_domains": list(include_domains),
        "exclude_domains": list(exclude_domains),
        "time_range": time_range,
        "search_depth": search_depth,
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
        click.echo("Error: Gateway not running. Start with 'sg start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("urls", nargs=-1, required=True)
@click.option("--provider", "-p", default=None, help="Extract provider")
@click.option("--format", "-f", default="markdown", type=click.Choice(["markdown", "text"]))
@click.option("--port", default=8100, help="Gateway port")
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.sg/config.json)")
def extract(urls: tuple[str], provider: str | None, format: str, port: int, config: str | None):
    """Extract content from URLs."""
    import httpx

    # Ensure gateway is running, start if needed
    ensure_gateway_running(port, config)
    try:
        resp = httpx.post(
            f"http://127.0.0.1:{port}/extract",
            json={"urls": list(urls), "provider": provider, "format": format},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        for r in data["results"]:
            click.echo(f"\n{'='*60}")
            click.echo(f"URL: {r['url']}")
            if r.get("title"):
                click.echo(f"Title: {r['title']}")
            click.echo(f"{'='*60}")
            if r.get("error"):
                click.echo(f"Error: {r['error']}")
            else:
                click.echo(r["content"])

    except httpx.ConnectError:
        click.echo("Error: Gateway not running. Start with 'sg start'", err=True)
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
        click.echo(resp.json()["content"])

    except httpx.ConnectError:
        click.echo("Error: Gateway not running. Start with 'sg start'", err=True)
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
                cb = f" [{m.get('circuit_breaker', 'closed')}]" if m.get('circuit_breaker') != 'closed' else ""
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
        click.echo("Gateway not running. Start with 'sg start'", err=True)
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
            fallback = f" (fallback: {','.join(p['fallback_for'])})" if p.get("fallback_for") else ""
            ptype = f" [{p.get('type', '')}]" if p.get("type") else ""
            cb = f" [circuit: {p['circuit_breaker']}]" if p.get("circuit_breaker") != "closed" else ""
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
        click.echo("Gateway not running. Start with 'sg start'", err=True)
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
        unhealthy_names = [u['name'] if isinstance(u, dict) else u for u in data.get('unhealthy', [])]
        click.echo(f"  Unhealthy: {', '.join(unhealthy_names) or 'None'}")

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'sg start'", err=True)
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
        click.echo("\nUse 'sg history <id>' to see full results.")

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'sg start'", err=True)
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
        "server": {
            "port": 8100
        },
        "providers": {
            "duckduckgo": {
                "type": "duckduckgo",
                "enabled": True,
                "priority": 100,
                "fallback_for": ["search"]
            }
        }
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
    click.echo("  sg start && sg web")
    click.echo("\nAvailable providers:")
    click.echo("  - Tavily (search, extract, research) - requires API key")
    click.echo("  - Exa (search, extract) - requires API key")
    click.echo("  - Brave (search) - requires API key")
    click.echo("  - You.com (search) - requires API key")
    click.echo("  - Firecrawl (extract) - requires API key")
    click.echo("  - Jina (extract) - free, no API key")
    click.echo("  - SearXNG (search) - requires self-hosted instance")
    click.echo("\nTest your setup:")
    click.echo("  sg search 'test query'")


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
def web(port: int):
    """Open Web UI in browser."""
    import webbrowser
    url = f"http://127.0.0.1:{port}"
    click.echo(f"Opening {url} ...")
    webbrowser.open(url)


if __name__ == "__main__":
    cli()
