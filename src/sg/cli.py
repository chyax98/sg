"""CLI — command line interface for Search Gateway."""

import asyncio
import json
import os
import sys
from pathlib import Path

import click


@click.group()
def cli():
    """Search Gateway — unified search with failover."""
    pass


@cli.command()
@click.option("--port", "-p", default=8100, help="Gateway port")
@click.option("--config", "-c", default="config.json", help="Config file path")
def start(port: int, config: str):
    """Start the gateway server."""
    import warnings
    os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"
    warnings.filterwarnings("ignore")

    click.echo(f"Starting Search Gateway on port {port}...")

    async def run():
        from .server.gateway import Gateway
        gateway = Gateway(config_path=config, port=port)
        await gateway.start()
        click.echo(f"\n  HTTP API:  http://127.0.0.1:{port}")
        click.echo(f"  Web UI:    http://127.0.0.1:{port}")
        click.echo(f"\n  Commands:  sg search 'query' | sg status | sg stop\n")
        await gateway.wait_shutdown()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        click.echo("\nGateway stopped.")


@cli.command()
@click.option("--config", "-c", default="config.json", help="Config file path")
def mcp(config: str):
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


@cli.command()
@click.argument("query")
@click.option("--provider", "-p", default=None, help="Search provider")
@click.option("--max", "-n", default=10, help="Max results")
@click.option("--include-domain", "include_domains", multiple=True, help="Restrict search to a domain")
@click.option("--exclude-domain", "exclude_domains", multiple=True, help="Exclude a domain from search")
@click.option("--time-range", type=click.Choice(["day", "week", "month", "year"]), default=None)
@click.option("--search-depth", type=click.Choice(["basic", "advanced", "fast", "ultra-fast"]), default="basic")
@click.option("--format", "-f", default="text", type=click.Choice(["text", "json", "markdown"]))
@click.option("--port", default=8100, help="Gateway port")
def search(
    query: str,
    provider: str | None,
    max: int,
    include_domains: tuple[str, ...],
    exclude_domains: tuple[str, ...],
    time_range: str | None,
    search_depth: str,
    format: str,
    port: int,
):
    """Execute a search query."""
    import httpx
    try:
        resp = httpx.post(
            f"http://127.0.0.1:{port}/search",
            json={
                "query": query,
                "provider": provider,
                "max_results": max,
                "include_domains": list(include_domains),
                "exclude_domains": list(exclude_domains),
                "time_range": time_range,
                "search_depth": search_depth,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if format == "json":
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            click.echo(f"\nSearch: {data['query']}")
            click.echo(f"  Provider: {data['provider']} | {data['total']} results | {data['latency_ms']:.0f}ms\n")
            for i, r in enumerate(data["results"], 1):
                click.echo(f"  [{i}] {r['title']}")
                click.echo(f"      {r['url']}")
                if r.get("content"):
                    content = r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"]
                    click.echo(f"      {content}")
                click.echo()

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
def extract(urls: tuple[str], provider: str | None, format: str, port: int):
    """Extract content from URLs."""
    import httpx
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
def research(topic: str, depth: str, port: int):
    """Execute deep research on a topic."""
    import httpx
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
def status(port: int):
    """Show gateway status."""
    import httpx
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        click.echo(f"\nSearch Gateway Status\n")
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
def providers(port: int):
    """List available providers."""
    import httpx
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/providers", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()

        click.echo(f"\nAvailable Providers\n")
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

        click.echo(f"\nHealth Check Results\n")
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
        click.echo(f"\nUse 'sg history <id>' to see full results.")

    except httpx.ConnectError:
        click.echo("Gateway not running. Start with 'sg start'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


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
