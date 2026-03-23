"""Tests for config models and migration."""

import json
import pytest
from pathlib import Path

from sg.models.config import (
    GatewayConfig, ProviderConfig, ExecutorConfig, Strategy,
    HealthCheckConfig, CircuitBreakerConfig, FailoverConfig,
)


class TestProviderConfig:

    def test_type_field(self):
        config = ProviderConfig(type="tavily", api_key="test")
        assert config.type == "tavily"

    def test_type_defaults_none(self):
        config = ProviderConfig()
        assert config.type is None

    def test_defaults(self):
        config = ProviderConfig()
        assert config.enabled is True
        assert config.priority == 10
        assert config.timeout == 30000
        assert config.is_fallback is False

    def test_no_weight_field(self):
        config = ProviderConfig()
        assert not hasattr(config, "weight")


class TestStrategy:

    def test_supported_strategies(self):
        assert Strategy.FAILOVER == "failover"
        assert Strategy.ROUND_ROBIN == "round_robin"
        assert Strategy.RANDOM == "random"
        assert len(Strategy) == 3


class TestExecutorConfig:

    def test_defaults(self):
        config = ExecutorConfig()
        assert config.strategy == Strategy.ROUND_ROBIN
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
            strategy=Strategy.RANDOM,
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
        assert config.strategy == Strategy.RANDOM
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
        assert config.version == "3.0"
        assert config.server.port == 8100
        assert config.providers == {}
        assert config.executor.strategy == Strategy.ROUND_ROBIN

    def test_missing_config_file_returns_default(self):
        config = GatewayConfig.load("/nonexistent/path/config.json")
        assert config.version == "3.0"
        assert config.providers == {}


class TestConfigMigration:

    def test_v1_migrated_to_v3(self, tmp_path):
        """V1 config with load_balancer is migrated to v3 executor."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "1.0",
            "providers": {
                "tavily": {
                    "enabled": True,
                    "api_key": "test",
                    "priority": 10,
                    "weight": 5,
                },
            },
            "routing": {"research": {"providers": ["tavily"]}},
            "default_providers": ["tavily"],
            "load_balancer": {"strategy": "weighted"},
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.version == "3.0"
        # weighted strategy migrated to round_robin
        assert config.executor.strategy == Strategy.ROUND_ROBIN
        # weight removed from provider config
        assert not hasattr(config.providers.get("tavily", ProviderConfig()), "weight")

    def test_v2_migrated_to_v3(self, tmp_path):
        """V2 config with load_balancer is migrated to v3 executor."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.0",
            "providers": {
                "tavily-main": {"type": "tavily", "api_key": "test", "priority": 1},
            },
            "load_balancer": {"strategy": "random"},
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.version == "3.0"
        assert config.executor.strategy == Strategy.RANDOM
        assert config.providers["tavily-main"].type == "tavily"

    def test_v3_not_migrated(self, tmp_path):
        """V3 config passes through without changes."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "3.0",
            "providers": {
                "tavily-main": {"type": "tavily", "api_key": "key1"},
            },
            "executor": {"strategy": "random"},
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.version == "3.0"
        assert config.executor.strategy == Strategy.RANDOM

    def test_round_robin_strategy_is_preserved(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.0",
            "load_balancer": {"strategy": "round_robin"},
        }))
        config = GatewayConfig.load(str(config_file))
        assert config.executor.strategy == Strategy.ROUND_ROBIN

    def test_multi_instance_same_type(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "3.0",
            "providers": {
                "tavily-main": {"type": "tavily", "api_key": "key1", "priority": 1},
                "tavily-backup": {"type": "tavily", "api_key": "key2", "priority": 5},
            },
        }))

        config = GatewayConfig.load(str(config_file))
        assert "tavily-main" in config.providers
        assert "tavily-backup" in config.providers
        assert config.providers["tavily-main"].api_key == "key1"
        assert config.providers["tavily-backup"].api_key == "key2"

    def test_save_raw(self, tmp_path):
        path = str(tmp_path / "out.json")
        data = {"version": "3.0", "providers": {"test": {"type": "tavily"}}}

        GatewayConfig.save_raw(data, path)

        loaded = json.loads(Path(path).read_text())
        assert loaded["version"] == "3.0"
        assert loaded["providers"]["test"]["type"] == "tavily"
