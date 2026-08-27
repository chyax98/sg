"""Local runtime state for discovering and reusing gateway instances."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

RUNTIME_ENV = "SEARCH_GATEWAY_RUNTIME_FILE"
RUNTIME_FILENAME = "runtime.json"


def runtime_path(path: str | Path | None = None) -> Path:
    """Return the runtime state path without creating it."""
    if path is not None:
        return Path(path).expanduser()
    configured = os.environ.get(RUNTIME_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".sg" / RUNTIME_FILENAME


def load_instances(path: str | Path | None = None) -> list[dict]:
    """Load runtime entries; malformed or missing state is treated as empty."""
    state_path = runtime_path(path)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    instances = payload.get("instances") if isinstance(payload, dict) else None
    return [entry for entry in instances if isinstance(entry, dict)] if isinstance(instances, list) else []


def latest_instance(path: str | Path | None = None) -> dict | None:
    """Return the most recently recorded instance."""
    instances = load_instances(path)
    return instances[-1] if instances else None


def record_instance(
    port: int,
    pid: int,
    *,
    mode: str,
    path: str | Path | None = None,
) -> dict:
    """Upsert one instance and atomically persist non-secret metadata."""
    state_path = runtime_path(path)
    instances = [entry for entry in load_instances(state_path) if entry.get("port") != port]
    entry = {
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "pid": pid,
        "mode": mode,
        "started_at": datetime.now(UTC).isoformat(),
    }
    instances.append(entry)
    _atomic_write(state_path, {"schema_version": 1, "instances": instances})
    return entry


def remove_instance(
    port: int,
    *,
    pid: int | None = None,
    path: str | Path | None = None,
) -> bool:
    """Remove an entry, preserving a newer process on the same port."""
    state_path = runtime_path(path)
    instances = load_instances(state_path)
    kept = [
        entry
        for entry in instances
        if entry.get("port") != port or (pid is not None and entry.get("pid") != pid)
    ]
    if len(kept) == len(instances):
        return False
    if kept:
        _atomic_write(state_path, {"schema_version": 1, "instances": kept})
    else:
        try:
            state_path.unlink()
        except FileNotFoundError:
            pass
    return True


def pid_for_port(port: int) -> int | None:
    """Find a listener PID on macOS/Linux when recovering an unrecorded instance."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    for line in result.stdout.splitlines():
        try:
            return int(line.strip())
        except ValueError:
            continue
    return None


@contextmanager
def startup_lock(path: str | Path | None = None) -> Iterator[None]:
    """Serialize local start attempts for the runtime state directory."""
    lock_path = runtime_path(path).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(mode=0o600, exist_ok=True)
    os.chmod(lock_path, 0o600)
    with lock_path.open("a+") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
            file.write("\n")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
