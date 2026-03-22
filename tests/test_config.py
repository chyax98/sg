"""Tests for config models and migration."""

import json
import pytest
import tempfile
from pathlib import Path

from sg.models.config import GatewayConfig, ProviderConfig, LSStrategy


class TestProviderConfig:

    def test_type_field(self):
        """ProviderConfig has optional type field."""
        config = ProviderConfig(type="tavily", api_key="test")
        assert config.type == "tavily"

    def test_type_defaults_none(self):
        """Type defaults to None."""
        config = ProviderConfig()
        assert config.type is None

    def test_no_weight_field(self):
        """Weight field removed from ProviderConfig."""
        config = ProviderConfig()
        assert not hasattr(config, "weight")


class TestLSStrategy:

    def test_only_failover_and_random(self):
        """Only failover and random strategies exist."""
        assert LSStrategy.FAILOVER == "failover"
        assert LSStrategy.RANDOM == "random"
        assert len(LSStrategy) == 2


class TestConfigMigration:

    def test_v1_to_v2_migration(self):
        """V1 config is migrated to v2."""
        v1 = {
            "version": "1.0",
            "providers": {
                "tavily": {"enabled": True, "api_key": "test", "priority": 10, "weight": 5},
                "brave": {"enabled": True, "api_key": "test2", "priority": 12, "weight": 3},
            },
            "routing": {
                "research": {"name": "research", "patterns": ["research"], "providers": ["tavily"]}
            },
            "default_providers": ["tavily", "brave"],
            "load_balancer": {"strategy": "weighted"},
        }

        result = GatewayConfig._migrate_v1_to_v2(v1)

        # Version updated
        assert result["version"] == "2.0"

        # Type field added
        assert result["providers"]["tavily"]["type"] == "tavily"
        assert result["providers"]["brave"]["type"] == "brave"

        # Weight removed
        assert "weight" not in result["providers"]["tavily"]

        # Routing removed
        assert "routing" not in result
        assert "default_providers" not in result

        # Strategy fixed
        assert result["load_balancer"]["strategy"] == "failover"

        # New sections added
        assert "mcp" in result
        assert "history" in result

    def test_load_v1_config(self, tmp_path):
        """Loading a v1 config auto-migrates."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "1.0",
            "providers": {
                "tavily": {"enabled": True, "api_key": "test", "weight": 5},
            },
            "load_balancer": {"strategy": "round_robin"},
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.version == "2.0"
        assert config.load_balancer.strategy == LSStrategy.FAILOVER

    def test_load_v2_config(self, tmp_path):
        """Loading a v2 config works directly."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.0",
            "providers": {
                "tavily-main": {"type": "tavily", "api_key": "test", "priority": 1},
            },
            "load_balancer": {"strategy": "random"},
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.version == "2.0"
        assert config.load_balancer.strategy == LSStrategy.RANDOM
        assert config.providers["tavily-main"].type == "tavily"

    def test_multi_instance_same_type(self, tmp_path):
        """Multiple instances of same provider type."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.0",
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

    def test_env_var_expansion(self, tmp_path, monkeypatch):
        """Environment variables are expanded."""
        monkeypatch.setenv("TEST_API_KEY", "expanded_key")

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.0",
            "providers": {
                "test": {"type": "tavily", "api_key": "${TEST_API_KEY}"},
            },
        }))

        config = GatewayConfig.load(str(config_file))
        assert config.providers["test"].api_key == "expanded_key"

    def test_load_raw_no_expansion(self, tmp_path, monkeypatch):
        """load_raw doesn't expand env vars."""
        monkeypatch.setenv("TEST_KEY", "expanded")

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {"test": {"api_key": "${TEST_KEY}"}},
        }))

        raw = GatewayConfig.load_raw(str(config_file))
        assert raw["providers"]["test"]["api_key"] == "${TEST_KEY}"

    def test_save_raw(self, tmp_path):
        """save_raw writes JSON to file."""
        path = str(tmp_path / "out.json")
        data = {"version": "2.0", "providers": {"test": {"type": "tavily"}}}

        GatewayConfig.save_raw(data, path)

        loaded = json.loads(Path(path).read_text())
        assert loaded["version"] == "2.0"
        assert loaded["providers"]["test"]["type"] == "tavily"

    def test_missing_config_returns_default(self):
        """Missing config file returns default config."""
        config = GatewayConfig.load("/nonexistent/path/config.json")
        assert config.version == "2.0"
        assert config.providers == {}
