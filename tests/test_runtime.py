"""Tests for local gateway instance discovery state."""

import stat

from sg._runtime import latest_instance, load_instances, record_instance, remove_instance


def test_record_instance_writes_private_state_and_upserts_by_port(tmp_path):
    state_path = tmp_path / "runtime.json"

    first = record_instance(9123, 101, mode="daemon", path=state_path)
    assert first["base_url"] == "http://127.0.0.1:9123"
    assert latest_instance(state_path)["pid"] == 101
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600

    record_instance(9123, 202, mode="launchd", path=state_path)
    updated = latest_instance(state_path)
    assert updated["port"] == first["port"]
    assert updated["base_url"] == first["base_url"]
    assert updated["pid"] == 202
    assert updated["mode"] == "launchd"


def test_remove_instance_does_not_remove_newer_process(tmp_path):
    state_path = tmp_path / "runtime.json"
    record_instance(9123, 101, mode="daemon", path=state_path)
    record_instance(9123, 202, mode="launchd", path=state_path)

    assert remove_instance(9123, pid=101, path=state_path) is False
    assert latest_instance(state_path)["pid"] == 202
    assert remove_instance(9123, pid=202, path=state_path) is True
    assert not state_path.exists()


def test_malformed_state_is_treated_as_empty(tmp_path):
    state_path = tmp_path / "runtime.json"
    state_path.write_text("not json", encoding="utf-8")

    assert load_instances(state_path) == []
    assert latest_instance(state_path) is None
