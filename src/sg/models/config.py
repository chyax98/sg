"""Configuration models."""

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel


class Strategy(str, Enum):
    """Provider selection strategy."""
    FAILOVER = "failover"       # always start from highest priority
    ROUND_ROBIN = "round_robin" # rotate across providers to spread load
    RANDOM = "random"           # random selection


class ProviderConfig(BaseModel):
    """Provider instance configuration."""
    type: str | None = None
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    priority: int = 10
    timeout: int = 30000
    is_fallback: bool = False
    env: dict[str, str] = {}


class HealthCheckConfig(BaseModel):
    """Health check thresholds."""
    failure_threshold: int = 3
    success_threshold: int = 2


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker settings with exponential backoff."""
    base_timeout: int = 3600        # 1 hour — first trip
    multiplier: float = 6.0         # 1h → 6h → 36h → ...
    max_timeout: int = 172800       # 48 hours cap
    quota_timeout: int = 86400      # 24h for quota exhaustion (429)
    auth_timeout: int = 604800      # 7 days for auth failures (401/403)


class FailoverConfig(BaseModel):
    """Failover execution settings."""
    max_attempts: int = 3


class ExecutorConfig(BaseModel):
    """Executor configuration."""
    strategy: Strategy = Strategy.ROUND_ROBIN
    health_check: HealthCheckConfig = HealthCheckConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    failover: FailoverConfig = FailoverConfig()


class ServerConfig(BaseModel):
    """HTTP server configuration."""
    host: str = "127.0.0.1"
    port: int = 8100


class MCPConfig(BaseModel):
    """MCP server configuration."""
    enabled: bool = False


class HistoryConfig(BaseModel):
    """Search history configuration."""
    enabled: bool = True
    dir: str = "~/.sg/history"
    max_entries: int = 10000


class WebUIConfig(BaseModel):
    """Web UI configuration."""
    enabled: bool = True


class GatewayConfig(BaseModel):
    """Main gateway configuration."""
    version: str = "3.0"
    server: ServerConfig = ServerConfig()
    providers: dict[str, ProviderConfig] = {}
    executor: ExecutorConfig = ExecutorConfig()
    mcp: MCPConfig = MCPConfig()
    history: HistoryConfig = HistoryConfig()
    web_ui: WebUIConfig = WebUIConfig()

    @classmethod
    def load(cls, path: str = "config.json") -> "GatewayConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        with open(config_path) as f:
            data = json.load(f)
        data = cls._migrate(data)
        return cls.model_validate(data)

    @classmethod
    def load_raw(cls, path: str = "config.json") -> dict:
        config_path = Path(path)
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            return json.load(f)

    @staticmethod
    def save_raw(data: dict, path: str = "config.json") -> None:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @classmethod
    def _migrate(cls, data: dict) -> dict:
        version = data.get("version", "1.0")
        if version == "3.0":
            return data

        if "load_balancer" in data:
            lb = data.pop("load_balancer")
            strategy = lb.get("strategy", "failover")
            if strategy in ("weighted", "least_connections"):
                strategy = "round_robin"
            data["executor"] = {
                "strategy": strategy,
                "health_check": lb.get("health_check", {}),
                "failover": lb.get("failover", {}),
            }

        data.pop("routing", None)
        data.pop("default_providers", None)
        data.pop("cache", None)

        for cfg in data.get("providers", {}).values():
            for dead_key in ("weight", "transport", "command", "args", "capabilities"):
                cfg.pop(dead_key, None)

        data["version"] = "3.0"
        return data


