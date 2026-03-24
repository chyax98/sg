"""Tests for config models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sg.models.config import (
    CircuitBreakerConfig,
    ExecutorConfig,
    FailoverConfig,
    GatewayConfig,
    HealthCheckConfig,
    InstanceSelection,
    ProviderConfig,
    ProviderInstanceConfig,
)


class TestProviderConfig:
    def test_defaults(self):
        config = ProviderConfig()
        assert config.type is None
        assert config.enabled is True
        assert config.priority == 10
        assert config.selection == InstanceSelection.RANDOM
        assert config.fallback_for == []
        assert config.defaults.timeout == 30000
        assert config.instances == []

    def test_group_with_instances(self):
        config = ProviderConfig(
            type="tavily",
            instances=[
                ProviderInstanceConfig(
                    id="t1",
                    api_key="key1",
                    url="https://example.com",
                    timeout=15000,
                )
            ],
        )
        instance = config.instances[0]
        assert instance.id == "t1"
        assert instance.api_key == "key1"
        assert instance.url == "https://example.com"
        assert instance.timeout == 15000





class TestExecutorConfig:
    def test_defaults(self):
        config = ExecutorConfig()
        assert config.health_check.failure_threshold == 3
        assert config.health_check.success_threshold == 2
        assert config.circuit_breaker.base_timeout == 3600
        assert config.circuit_breaker.multiplier == 6.0
        assert config.circuit_breaker.max_timeout == 172800
        assert config.circuit_breaker.quota_timeout == 86400
        assert config.circuit_breaker.auth_timeout == 604800
        assert config.failover.max_attempts == 3

    def test_custom_values(self):
        config = ExecutorConfig(
            health_check=HealthCheckConfig(failure_threshold=5),
            circuit_breaker=CircuitBreakerConfig(
                base_timeout=120,
                multiplier=2.0,
                max_timeout=3600,
                quota_timeout=1800,
                auth_timeout=7200,
            ),
            failover=FailoverConfig(max_attempts=5),
        )
        assert config.health_check.failure_threshold == 5
        assert config.circuit_breaker.base_timeout == 120
        assert config.circuit_breaker.multiplier == 2.0
        assert config.circuit_breaker.max_timeout == 3600
        assert config.circuit_breaker.quota_timeout == 1800
        assert config.circuit_breaker.auth_timeout == 7200
        assert config.failover.max_attempts == 5


class TestGatewayConfig:
    def test_default_config(self):
        config = GatewayConfig()
        assert config.server.port == 8100
        assert config.providers == {}

    def test_missing_config_file_returns_default(self):
        config = GatewayConfig.load("/nonexistent/path/config.json")
        assert config.providers == {}
        assert config.server.host == "127.0.0.1"

    def test_loads_current_grouped_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "providers": {
                        "exa": {
                            "type": "exa",
                            "priority": 1,
                            "selection": "random",
                            "defaults": {"timeout": 30000},
                            "instances": [
                                {
                                    "id": "exa-1",
                                    "api_key": "key1",
                                    "url": "https://api.example.com",
                                }
                            ],
                        }
                    },
                    "executor": {"strategy": "random"},
                }
            )
        )

        config = GatewayConfig.load(str(config_file))
        assert config.providers["exa"].instances[0].url == "https://api.example.com"

    def test_rejects_unknown_root_fields(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"version": "4.0"}))

        with pytest.raises(ValidationError):
            GatewayConfig.load(str(config_file))

    def test_rejects_flat_provider_shape(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "providers": {
                        "tavily-main": {"type": "tavily", "api_key": "key1"}
                    }
                }
            )
        )

        with pytest.raises(ValidationError):
            GatewayConfig.load(str(config_file))

    def test_save_raw(self, tmp_path):
        path = str(tmp_path / "out.json")
        data = {
            "providers": {
                "test": {
                    "type": "tavily",
                    "instances": [],
                }
            }
        }

        GatewayConfig.save_raw(data, path)

        loaded = json.loads(Path(path).read_text())
        assert "version" not in loaded
        assert loaded["providers"]["test"]["type"] == "tavily"
