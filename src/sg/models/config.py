"""Configuration models."""

import json
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class TransportType(str, Enum):
    HTTP = "http"
    STDIO = "stdio"


class LSStrategy(str, Enum):
    """Load balancing strategy."""
    FAILOVER = "failover"
    RANDOM = "random"


class ProviderConfig(BaseModel):
    """Provider configuration."""
    type: str | None = None  # provider type (tavily, brave, etc.). Inferred from key if missing.
    enabled: bool = True
    transport: TransportType = TransportType.HTTP
    url: str | None = None
    api_key: str | None = None
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    priority: int = 10
    timeout: int = 30000
    capabilities: list[str] = ["search"]
    is_fallback: bool = False


class HealthCheckConfig(BaseModel):
    """Health check configuration."""
    enabled: bool = True
    interval: int = 30
    timeout: int = 5
    failure_threshold: int = 3
    success_threshold: int = 2


class FailoverConfig(BaseModel):
    """Failover configuration."""
    enabled: bool = True
    retry_count: int = 2
    retry_delay: int = 1000


class LoadBalancerConfig(BaseModel):
    """Load balancer configuration."""
    strategy: LSStrategy = LSStrategy.FAILOVER
    health_check: HealthCheckConfig = HealthCheckConfig()
    failover: FailoverConfig = FailoverConfig()


class CacheConfig(BaseModel):
    """Cache configuration."""
    enabled: bool = True
    ttl: int = 300
    max_size: int = 1000


class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = "127.0.0.1"
    port: int = 8100
    transports: list[str] = ["http"]


class WebUIConfig(BaseModel):
    """Web UI configuration."""
    enabled: bool = True


class MCPConfig(BaseModel):
    """MCP server configuration."""
    enabled: bool = False


class HistoryConfig(BaseModel):
    """Search history configuration."""
    enabled: bool = True
    dir: str = "~/.sg/history"
    max_entries: int = 10000


class GatewayConfig(BaseModel):
    """Main gateway configuration."""
    version: str = "2.0"
    server: ServerConfig = ServerConfig()
    providers: dict[str, ProviderConfig] = {}
    load_balancer: LoadBalancerConfig = LoadBalancerConfig()
    cache: CacheConfig = CacheConfig()
    web_ui: WebUIConfig = WebUIConfig()
    mcp: MCPConfig = MCPConfig()
    history: HistoryConfig = HistoryConfig()

    @classmethod
    def load(cls, path: str = "config.json") -> "GatewayConfig":
        """Load configuration from file."""
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = json.load(f)

        # Auto-migrate v1 config
        if data.get("version", "1.0") == "1.0":
            data = cls._migrate_v1_to_v2(data)

        data = cls._expand_env_vars(data)
        return cls.model_validate(data)

    @classmethod
    def load_raw(cls, path: str = "config.json") -> dict:
        """Load raw config JSON without env var expansion."""
        config_path = Path(path)
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            return json.load(f)

    @staticmethod
    def save_raw(data: dict, path: str = "config.json") -> None:
        """Save raw config dict to file."""
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    @staticmethod
    def _migrate_v1_to_v2(data: dict) -> dict:
        """Migrate v1 config to v2 format."""
        # Add type field to providers where missing
        for name, config in data.get("providers", {}).items():
            if "type" not in config:
                config["type"] = name
            # Remove weight
            config.pop("weight", None)

        # Remove routing section
        data.pop("routing", None)
        data.pop("default_providers", None)

        # Fix strategy
        lb = data.get("load_balancer", {})
        if lb.get("strategy") in ("round_robin", "weighted", "least_connections"):
            lb["strategy"] = "failover"

        # Remove web_ui.port (no longer separate)
        web_ui = data.get("web_ui", {})
        web_ui.pop("port", None)

        # Set version
        data["version"] = "2.0"

        # Add defaults for new sections
        data.setdefault("mcp", {"enabled": False})
        data.setdefault("history", {"enabled": True, "dir": "~/.sg/history"})

        return data

    @staticmethod
    def _expand_env_vars(data: Any) -> Any:
        """Expand environment variables in config."""
        if isinstance(data, str):
            pattern = r'\$\{([^}:]+)(?::-([^}]*))?\}'

            def replace(match):
                var = match.group(1)
                default = match.group(2) or ""
                return os.environ.get(var, default)
            return re.sub(pattern, replace, data)
        elif isinstance(data, dict):
            return {k: GatewayConfig._expand_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [GatewayConfig._expand_env_vars(item) for item in data]
        return data
