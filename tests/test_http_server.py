"""Tests for HTTP server security behavior."""

from fastapi.testclient import TestClient

from sg.models.config import GatewayConfig
from sg.server.http_server import HTTPServer


class _DummyGateway:
    def __init__(self):
        self.config = GatewayConfig()

    async def get_status(self):
        return {
            "running": True,
            "port": 8100,
            "providers": {"total": 0, "available": []},
            "metrics": {},
        }

    def get_config_raw(self):
        return {"providers": {}}

    async def stop(self):
        return None


class TestHTTPServerSecurity:
    def test_cross_origin_reads_do_not_get_cors_headers(self):
        server = HTTPServer(_DummyGateway(), port=8100)
        client = TestClient(server.app)

        response = client.get("/api/config", headers={"Origin": "https://evil.example"})

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") is None

    def test_cross_origin_shutdown_is_rejected(self):
        server = HTTPServer(_DummyGateway(), port=8100)
        client = TestClient(server.app)

        response = client.post("/shutdown", headers={"Origin": "https://evil.example"})

        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin browser requests are not allowed"

    def test_non_browser_shutdown_request_is_allowed(self):
        server = HTTPServer(_DummyGateway(), port=8100)
        client = TestClient(server.app)

        response = client.post("/shutdown")

        assert response.status_code == 200
        assert response.json() == {"status": "shutting down"}
