"""HTTP Server - REST API for search gateway."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

WEB_UI_PATH = Path(__file__).parent.parent.parent.parent / "web" / "index.html"


class SearchBody(BaseModel):
    query: str
    provider: str | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    time_range: str | None = None
    extra: dict[str, Any] = {}


class ExtractBody(BaseModel):
    urls: list[str]
    provider: str | None = None
    format: str = "markdown"
    extract_depth: str = "basic"


class ResearchBody(BaseModel):
    topic: str
    depth: str = "auto"
    provider: str | None = None


class ProviderBody(BaseModel):
    type: str
    api_key: str | None = None
    url: str | None = None
    enabled: bool = True
    priority: int = 10
    timeout: int = 30000
    is_fallback: bool = False
    env: dict[str, str] = {}


class SettingsBody(BaseModel):
    strategy: str | None = None
    mcp_enabled: bool | None = None
    history_enabled: bool | None = None


class HTTPServer:
    """HTTP REST API server."""

    def __init__(self, gateway, port: int):
        self.gateway = gateway
        self.port = port
        self.app = FastAPI(title="Search Gateway", version="2.0.0")
        self._server = None

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._setup_routes()

    def _setup_routes(self):
        # === Web UI ===
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            if WEB_UI_PATH.exists():
                return HTMLResponse(content=WEB_UI_PATH.read_text(), status_code=200)
            return HTMLResponse(content="<h1>Search Gateway</h1><p>Web UI not found</p>")

        # === Search API ===
        @self.app.get("/api")
        async def api_info():
            return {"name": "Search Gateway", "version": "2.0.0"}

        @self.app.post("/search")
        async def search(body: SearchBody):
            try:
                result = await self.gateway.search(
                    query=body.query, provider=body.provider,
                    max_results=body.max_results,
                    include_domains=body.include_domains,
                    exclude_domains=body.exclude_domains,
                    time_range=body.time_range, extra=body.extra,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Search error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/extract")
        async def extract(body: ExtractBody):
            try:
                result = await self.gateway.extract(
                    urls=body.urls, provider=body.provider,
                    format=body.format, extract_depth=body.extract_depth,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Extract error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/research")
        async def research(body: ResearchBody):
            try:
                result = await self.gateway.research(
                    topic=body.topic, depth=body.depth, provider=body.provider,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Research error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/providers")
        async def list_providers():
            providers = await self.gateway.list_providers()
            return [p.model_dump() for p in providers]

        @self.app.get("/status")
        async def get_status():
            return await self.gateway.get_status()

        @self.app.post("/health-check")
        async def health_check():
            return await self.gateway.health_check()

        @self.app.get("/metrics")
        async def get_metrics():
            return self.gateway.load_balancer.get_metrics()

        @self.app.post("/shutdown")
        async def shutdown():
            asyncio.create_task(self._delayed_shutdown())
            return {"status": "shutting down"}

        # === Config API ===
        @self.app.get("/api/config")
        async def get_config():
            """Get raw config (without env var expansion)."""
            return self.gateway.get_config_raw()

        @self.app.get("/api/provider-types")
        async def get_provider_types():
            """List available provider types."""
            return self.gateway.get_provider_types()

        @self.app.put("/api/config/providers/{instance_id}")
        async def upsert_provider(instance_id: str, body: ProviderBody):
            """Add or update a provider instance."""
            raw = self.gateway.get_config_raw()
            if "providers" not in raw:
                raw["providers"] = {}

            raw["providers"][instance_id] = {
                "type": body.type,
                "enabled": body.enabled,
                "priority": body.priority,
                "timeout": body.timeout,
                "is_fallback": body.is_fallback,
            }
            if body.api_key is not None:
                raw["providers"][instance_id]["api_key"] = body.api_key
            if body.url is not None:
                raw["providers"][instance_id]["url"] = body.url
            if body.env:
                raw["providers"][instance_id]["env"] = body.env

            self.gateway.save_config_raw(raw)
            return {"status": "ok", "instance_id": instance_id}

        @self.app.delete("/api/config/providers/{instance_id}")
        async def delete_provider(instance_id: str):
            """Delete a provider instance."""
            raw = self.gateway.get_config_raw()
            providers = raw.get("providers", {})
            if instance_id not in providers:
                raise HTTPException(status_code=404, detail=f"Provider '{instance_id}' not found")

            del providers[instance_id]
            self.gateway.save_config_raw(raw)
            return {"status": "ok", "deleted": instance_id}

        @self.app.put("/api/config/settings")
        async def update_settings(body: SettingsBody):
            """Update general settings."""
            raw = self.gateway.get_config_raw()

            if body.strategy is not None:
                raw.setdefault("load_balancer", {})["strategy"] = body.strategy
            if body.mcp_enabled is not None:
                raw.setdefault("mcp", {})["enabled"] = body.mcp_enabled
            if body.history_enabled is not None:
                raw.setdefault("history", {})["enabled"] = body.history_enabled

            self.gateway.save_config_raw(raw)
            return {"status": "ok"}

        @self.app.post("/api/config/reload")
        async def reload_config():
            """Reload config and reinitialize providers."""
            try:
                await self.gateway.reload_config()
                return {"status": "ok"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # === History API ===
        @self.app.get("/api/history")
        async def list_history(limit: int = 50, offset: int = 0):
            """List recent searches."""
            entries = await self.gateway.history.list(limit=limit, offset=offset)
            return [e.model_dump() for e in entries]

        @self.app.get("/api/history/{entry_id}")
        async def get_history_entry(entry_id: str):
            """Get single history entry with full results."""
            entry = await self.gateway.history.get(entry_id)
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            return entry.model_dump()

        @self.app.delete("/api/history")
        async def clear_history():
            """Clear all history."""
            count = await self.gateway.history.clear()
            return {"status": "ok", "deleted": count}

    async def _delayed_shutdown(self):
        await asyncio.sleep(0.5)
        await self.gateway.stop()

    async def start(self):
        import logging
        logging.getLogger("uvicorn").setLevel(logging.ERROR)
        logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

        config = uvicorn.Config(
            self.app, host="0.0.0.0", port=self.port, log_level="error",
        )
        self._server = uvicorn.Server(config)
        asyncio.create_task(self._server.serve())
        logger.info(f"HTTP server started on port {self.port}")

    async def stop(self):
        if self._server:
            self._server.should_exit = True
