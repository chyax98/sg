"""HTTP Server — REST API for search gateway."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..models.config import InstanceSelection, ProviderDefaultsConfig
from ..providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)

# Try multiple locations for Web UI
def _find_web_ui() -> Path | None:
    # Development mode: relative to source
    dev_path = Path(__file__).parent.parent.parent.parent / "web" / "index.html"
    if dev_path.exists():
        return dev_path

    # Installed mode: in share directory
    if sys.prefix:
        installed_path = Path(sys.prefix) / "share" / "search-gateway" / "web" / "index.html"
        if installed_path.exists():
            return installed_path

    return None

WEB_UI_PATH = _find_web_ui()


# === Request bodies ===

class SearchBody(BaseModel):
    query: str
    provider: str | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    time_range: str | None = None
    search_depth: str = "basic"
    extra: dict[str, Any] = Field(default_factory=dict)


class ExtractBody(BaseModel):
    urls: list[str]
    provider: str | None = None
    format: str = "markdown"
    extract_depth: str = "basic"
    extra: dict[str, Any] = Field(default_factory=dict)


class ResearchBody(BaseModel):
    topic: str
    depth: str = "auto"
    provider: str | None = None


class SearchBatchBody(BaseModel):
    queries: list[str]
    provider: str | None = None
    max_results: int = Field(default=10, ge=1, le=50)
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    time_range: str | None = None
    search_depth: str = "basic"
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderBody(BaseModel):
    type: str
    enabled: bool = True
    priority: int = 10
    selection: InstanceSelection = InstanceSelection.RANDOM
    fallback_for: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    defaults: ProviderDefaultsConfig = Field(default_factory=ProviderDefaultsConfig)


class ProviderInstanceBody(BaseModel):
    enabled: bool = True
    api_key: str | None = None
    url: str | None = None
    timeout: int | None = None
    priority: int = 10
    env: dict[str, str] = Field(default_factory=dict)




class HTTPServer:
    """HTTP REST API server."""

    def __init__(self, gateway, port: int, host: str = "127.0.0.1"):
        self.gateway = gateway
        self.port = port
        self.host = host
        self.app = FastAPI(title="Search Gateway")
        self._server: uvicorn.Server | None = None

        self._setup_security()
        self._setup_routes()

    def _setup_security(self) -> None:
        @self.app.middleware("http")
        async def protect_mutating_requests(request: Request, call_next):
            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                origin = request.headers.get("origin")
                if origin and not self._is_same_origin(origin, request):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Cross-origin browser requests are not allowed"},
                    )
            return await call_next(request)

    @staticmethod
    def _is_same_origin(origin: str, request: Request) -> bool:
        """Allow browser writes only from the gateway's own origin."""
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        request_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
        return origin == request_origin

    def _setup_routes(self):
        gw = self.gateway

        # === Web UI ===

        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            if WEB_UI_PATH and WEB_UI_PATH.exists():
                return HTMLResponse(content=WEB_UI_PATH.read_text(), status_code=200)
            return HTMLResponse(content="<h1>Search Gateway</h1><p>Web UI not found</p>")

        # === Core API ===

        @self.app.post("/search")
        async def search(body: SearchBody):
            try:
                result = await gw.search(
                    query=body.query, provider=body.provider,
                    max_results=body.max_results,
                    include_domains=body.include_domains,
                    exclude_domains=body.exclude_domains,
                    time_range=body.time_range,
                    search_depth=body.search_depth,
                    extra=body.extra,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Search error: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @self.app.post("/search/batch")
        async def search_batch(body: SearchBatchBody):
            try:
                results = await gw.search_batch(
                    queries=body.queries, provider=body.provider,
                    max_results=body.max_results,
                    include_domains=body.include_domains,
                    exclude_domains=body.exclude_domains,
                    time_range=body.time_range,
                    search_depth=body.search_depth,
                    extra=body.extra,
                )
                return [r.model_dump() for r in results]
            except Exception as e:
                logger.error(f"Batch search error: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @self.app.post("/extract")
        async def extract(body: ExtractBody):
            try:
                result = await gw.extract(
                    urls=body.urls, provider=body.provider,
                    format=body.format, extract_depth=body.extract_depth,
                    extra=body.extra,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Extract error: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @self.app.post("/research")
        async def research(body: ResearchBody):
            try:
                result = await gw.research(
                    topic=body.topic, depth=body.depth, provider=body.provider,
                )
                return result.model_dump()
            except Exception as e:
                logger.error(f"Research error: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        # === Operational API ===

        @self.app.get("/providers")
        async def list_providers():
            providers = await gw.list_providers()
            result = []
            for p in providers:
                d = p.model_dump()
                breaker = gw.executor.get_breaker_status(p.name)
                d["circuit_breaker"] = breaker["state"]
                d["healthy"] = breaker["state"] != "open"
                d["disabled_seconds_remaining"] = breaker["remaining_disabled_seconds"]
                d["last_failure_type"] = breaker["last_failure_type"]
                d["trip_count"] = breaker["trip_count"]
                result.append(d)
            return result

        @self.app.get("/status")
        async def get_status():
            return await gw.get_status()

        @self.app.post("/health-check")
        async def health_check():
            return await gw.health_check()

        @self.app.get("/metrics")
        async def get_metrics():
            return gw.executor.get_metrics()

        @self.app.post("/shutdown")
        async def shutdown():
            asyncio.create_task(self._delayed_shutdown())
            return {"status": "shutting down"}

        # === Config API ===

        @self.app.get("/api/config")
        async def get_config():
            return gw.get_config_raw()

        @self.app.get("/api/provider-types")
        async def get_provider_types():
            return ProviderRegistry.get_provider_types()

        @self.app.put("/api/config/providers/{provider_id}")
        async def upsert_provider(provider_id: str, body: ProviderBody):
            raw = gw.get_config_raw()
            raw.setdefault("providers", {})[provider_id] = {
                "type": body.type,
                "enabled": body.enabled,
                "priority": body.priority,
                "selection": body.selection.value,
                "fallback_for": body.fallback_for,
                "tags": body.tags,
                "defaults": body.defaults.model_dump(),
                "instances": raw.get("providers", {}).get(provider_id, {}).get("instances", []),
            }
            gw.save_config_raw(raw)
            return {"status": "ok", "provider_id": provider_id}

        @self.app.delete("/api/config/providers/{provider_id}")
        async def delete_provider(provider_id: str):
            raw = gw.get_config_raw()
            providers = raw.get("providers", {})
            if provider_id not in providers:
                raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
            del providers[provider_id]
            gw.save_config_raw(raw)
            return {"status": "ok", "deleted": provider_id}

        @self.app.put("/api/config/providers/{provider_id}/instances/{instance_id}")
        async def upsert_provider_instance(provider_id: str, instance_id: str, body: ProviderInstanceBody):
            raw = gw.get_config_raw()
            provider_cfg = raw.setdefault("providers", {}).setdefault(
                provider_id,
                {
                    "type": provider_id,
                    "enabled": True,
                    "priority": 10,
                    "selection": "random",
                    "defaults": {},
                    "instances": [],
                },
            )
            instances = provider_cfg.setdefault("instances", [])
            instance_payload = {
                "id": instance_id,
                "enabled": body.enabled,
                "priority": body.priority,
                **({"api_key": body.api_key} if body.api_key is not None else {}),
                **({"url": body.url} if body.url is not None else {}),
                **({"timeout": body.timeout} if body.timeout is not None else {}),
                **({"env": body.env} if body.env else {}),
            }

            replaced = False
            for idx, existing in enumerate(instances):
                if existing.get("id") == instance_id:
                    instances[idx] = instance_payload
                    replaced = True
                    break
            if not replaced:
                instances.append(instance_payload)

            gw.save_config_raw(raw)
            return {"status": "ok", "provider_id": provider_id, "instance_id": instance_id}

        @self.app.delete("/api/config/providers/{provider_id}/instances/{instance_id}")
        async def delete_provider_instance(provider_id: str, instance_id: str):
            raw = gw.get_config_raw()
            provider_cfg = raw.get("providers", {}).get(provider_id)
            if not provider_cfg:
                raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
            instances = provider_cfg.get("instances", [])
            new_instances = [item for item in instances if item.get("id") != instance_id]
            if len(new_instances) == len(instances):
                raise HTTPException(status_code=404, detail=f"Instance '{instance_id}' not found")
            provider_cfg["instances"] = new_instances
            gw.save_config_raw(raw)
            return {"status": "ok", "provider_id": provider_id, "deleted": instance_id}



        @self.app.post("/api/config/reload")
        async def reload_config():
            try:
                await gw.reload_config()
                return {"status": "ok"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

        # === History API ===

        @self.app.get("/api/history")
        async def list_history(limit: int = 50, offset: int = 0):
            entries = await gw.history.list(limit=limit, offset=offset)
            return [e.model_dump() for e in entries]

        @self.app.get("/api/history/{entry_id}")
        async def get_history_entry(entry_id: str):
            entry = await gw.history.get(entry_id)
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            return entry.model_dump()

        @self.app.delete("/api/history")
        async def clear_history():
            count = await gw.history.clear()
            return {"status": "ok", "deleted": count}

    async def _delayed_shutdown(self):
        await asyncio.sleep(0.5)
        await self.gateway.stop()

    async def start(self):
        logging.getLogger("uvicorn").setLevel(logging.ERROR)
        logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
        logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="error",
            ws="wsproto",  # Use wsproto instead of websockets to avoid deprecation warnings
        )
        self._server = uvicorn.Server(config)
        asyncio.create_task(self._server.serve())
        logger.info(f"HTTP server on {self.host}:{self.port}")

    async def stop(self):
        if self._server:
            self._server.should_exit = True
