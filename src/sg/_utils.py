"""Utility functions for CLI."""

import subprocess
import sys
import time

import httpx


def is_gateway_running(port: int = 8100) -> bool:
    """Check if gateway is running by trying to connect."""
    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=1.0)
        return resp.status_code == 200
    except Exception:
        return False


def start_gateway_background(port: int = 8100, config: str | None = None) -> bool:
    """Start gateway in background if not running. Returns True if started."""
    if is_gateway_running(port):
        return False

    # Start gateway in background using subprocess
    cmd = [sys.executable, "-m", "sg", "start", "--port", str(port)]
    if config:
        cmd.extend(["--config", config])

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as e:
        raise RuntimeError(f"Failed to start gateway background process: {e}") from e

    # Wait for gateway to be ready (max 10 seconds)
    for _ in range(20):
        time.sleep(0.5)
        if is_gateway_running(port):
            return True

    return False


def ensure_gateway_running(port: int = 8100, config: str | None = None) -> bool:
    """Ensure gateway is running, start if needed. Returns True if running."""
    if is_gateway_running(port):
        return True
    start_gateway_background(port, config)
    if is_gateway_running(port):
        return True
    raise RuntimeError(f"Gateway failed to start on port {port}")
