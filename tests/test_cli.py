"""Tests for the command-line interface contracts."""

from contextlib import nullcontext

from click.testing import CliRunner

from sg import cli as cli_module


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_search_help_describes_inline_output():
    result = CliRunner().invoke(cli_module.cli, ["search", "--help"])

    assert result.exit_code == 0
    assert "print inline results" in result.output
    assert "result file" not in result.output


def test_cli_version_is_available():
    result = CliRunner().invoke(cli_module.cli, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "search-gateway, version 1.0.8"


def test_history_list_includes_id(monkeypatch):
    entry_id = "1787753227538-75c5dcf0"
    monkeypatch.setattr(
        cli_module.httpx,
        "get",
        lambda *args, **kwargs: _Response(
            [
                {
                    "id": entry_id,
                    "timestamp": "2026-08-27T10:00:00.000000",
                    "provider": "duckduckgo",
                    "query": "test query",
                    "total": 1,
                }
            ]
        ),
    )

    result = CliRunner().invoke(cli_module.cli, ["history", "-n", "1"])

    assert result.exit_code == 0
    assert f"id={entry_id}" in result.output
    assert "Use 'search-gateway history <id>'" in result.output


def test_search_allows_time_for_provider_failover(monkeypatch):
    captured = {}

    monkeypatch.setattr(cli_module, "_ensure_gateway_or_exit", lambda *args: None)

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return _Response(
            {
                "query": "test",
                "provider": "duckduckgo",
                "results": [{"title": "Result", "url": "https://example.com"}],
            }
        )

    monkeypatch.setattr(cli_module.httpx, "post", fake_post)

    result = CliRunner().invoke(cli_module.cli, ["search", "test"])

    assert result.exit_code == 0
    assert captured["timeout"] == 180.0


def test_extract_allows_time_for_provider_failover(monkeypatch):
    captured = {}

    monkeypatch.setattr(cli_module, "_ensure_gateway_or_exit", lambda *args: None)

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return _Response(
            {
                "provider": "jina-1",
                "results": [
                    {"url": "https://example.com", "title": "Example", "content": "body"}
                ],
            }
        )

    monkeypatch.setattr(cli_module.httpx, "post", fake_post)

    result = CliRunner().invoke(cli_module.cli, ["extract", "https://example.com"])

    assert result.exit_code == 0
    assert captured["timeout"] == 300.0


def test_commands_reuse_latest_runtime_port(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli_module, "latest_instance", lambda: {"port": 9123, "pid": 42})

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _Response([])

    monkeypatch.setattr(cli_module.httpx, "get", fake_get)

    result = CliRunner().invoke(cli_module.cli, ["history", "-n", "1"])

    assert result.exit_code == 0
    assert captured["url"] == "http://127.0.0.1:9123/api/history"


def test_start_reuses_running_instance(monkeypatch):
    monkeypatch.setattr(cli_module, "startup_lock", lambda: nullcontext())
    monkeypatch.setattr(cli_module, "is_gateway_running", lambda port: port == 9123)
    monkeypatch.setattr(cli_module, "_record_existing_instance", lambda port: None)

    result = CliRunner().invoke(cli_module.cli, ["start", "--port", "9123"])

    assert result.exit_code == 0
    assert "Gateway already running; reusing http://127.0.0.1:9123" in result.output


def test_existing_instance_refreshes_stale_pid(monkeypatch):
    recorded = {}
    monkeypatch.setattr(cli_module, "latest_instance", lambda: {"port": 9123, "pid": 101})
    monkeypatch.setattr(cli_module, "pid_for_port", lambda port: 202)
    monkeypatch.setattr(
        cli_module,
        "record_instance",
        lambda port, pid, *, mode: recorded.update(port=port, pid=pid, mode=mode),
    )

    cli_module._record_existing_instance(9123)

    assert recorded == {"port": 9123, "pid": 202, "mode": "existing"}


def test_stop_removes_only_recorded_instance(monkeypatch):
    removed = {}
    monkeypatch.setattr(cli_module, "latest_instance", lambda: {"port": 9123, "pid": 101})
    monkeypatch.setattr(cli_module.httpx, "post", lambda *args, **kwargs: _Response({}))
    monkeypatch.setattr(
        cli_module,
        "remove_instance",
        lambda port, *, pid=None: removed.update(port=port, pid=pid),
    )

    result = CliRunner().invoke(cli_module.cli, ["stop", "--port", "9123"])

    assert result.exit_code == 0
    assert removed == {"port": 9123, "pid": 101}
