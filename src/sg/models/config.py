"""Configuration models."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def resolve_config_path(path: str | None = None) -> Path:
    """Resolve config file path: --config parameter > ~/.sg/config.json (default)"""
    if path:
        return Path(path).expanduser()

    # Always use global config, never fall back to project directory
    return Path.home() / ".sg" / "config.json"


class StrictConfigModel(BaseModel):
    """Base config model. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class InstanceSelection(StrEnum):
    """Within-provider instance selection strategy."""

    RANDOM = "random"
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"


class ProviderDefaultsConfig(StrictConfigModel):
    """Shared provider-level defaults inherited by instances."""

    timeout: int = 30000


class ProviderInstanceConfig(StrictConfigModel):
    """Concrete provider instance configuration."""

    id: str
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    timeout: int | None = None
    priority: int = 10
    env: dict[str, str] = Field(default_factory=dict)


class ProviderConfig(StrictConfigModel):
    """Provider group configuration."""

    type: str | None = None
    enabled: bool = True
    priority: int = 10
    selection: InstanceSelection = InstanceSelection.RANDOM
    fallback_for: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    defaults: ProviderDefaultsConfig = Field(default_factory=ProviderDefaultsConfig)
    instances: list[ProviderInstanceConfig] = Field(default_factory=list)


class HealthCheckConfig(StrictConfigModel):
    """Health check thresholds."""

    failure_threshold: int = 3
    success_threshold: int = 2


class CircuitBreakerConfig(StrictConfigModel):
    """Circuit breaker settings with exponential backoff.

    Defaults suit a local free-key pool: short cool-downs, not multi-day bans.
    """

    base_timeout: int = 300  # 5 minutes
    multiplier: float = 2.0
    max_timeout: int = 3600  # 1 hour cap
    quota_timeout: int = 3600  # 1 hour on 429
    auth_timeout: int = 86400  # 1 day on 401/403


class FailoverConfig(StrictConfigModel):
    """Failover execution settings.

    max_attempts: max provider *groups* to try (not instances).
    <= 0 means try every candidate group (recommended for free-key pools).
    """

    max_attempts: int = 0


class ExecutorConfig(StrictConfigModel):
    """Executor configuration."""

    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)


class ServerConfig(StrictConfigModel):
    """HTTP server configuration."""

    host: str = "127.0.0.1"
    port: int = 8100


class HistoryConfig(StrictConfigModel):
    """Search history configuration."""

    dir: str = "~/.sg/history"
    max_entries: int = 10000


class WebUIConfig(StrictConfigModel):
    """Web UI configuration."""

    enabled: bool = True


class GatewayConfig(StrictConfigModel):
    """Main gateway configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    web_ui: WebUIConfig = Field(default_factory=WebUIConfig)

    @classmethod
    def load(cls, path: str | None = None) -> "GatewayConfig":
        config_path = resolve_config_path(path)
        if not config_path.exists():
            return cls()
        with open(config_path) as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def load_raw(cls, path: str | None = None) -> dict[str, Any]:
        config_path = resolve_config_path(path)
        if not config_path.exists():
            return {}
        with open(config_path) as f:
            data: dict[str, Any] = json.load(f)
            return data

    @staticmethod
    def save_raw(data: dict, path: str | None = None) -> None:
        config_path = resolve_config_path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
