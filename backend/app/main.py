import asyncio
import contextlib
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import install_handlers
from app.core.events import broker
from app.core.logging import configure_logging, get_logger
from app.modules.ai.router import router as ai_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.dashboards.router import router as dashboards_router
from app.modules.datasets.router import router as datasets_router
from app.modules.devices.router import router as devices_router
from app.modules.display.router import router as display_router
from app.modules.health.router import router as health_router
from app.modules.iam.router import router as iam_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.query import executor
from app.modules.settings.router import router as settings_router

log = get_logger("api")
HTTP_REQS = Counter("http_requests_total", "Requisicoes HTTP", ["method", "route", "status"])
HTTP_LAT = Histogram("http_request_duration_seconds", "Latencia HTTP", ["route"])
SSE_CONNS = Gauge("sse_connections", "Conexoes SSE abertas")
CACHE_HITS = Gauge("query_cache_hits", "Hits do cache de consultas")
CACHE_MISSES = Gauge("query_cache_misses", "Misses do cache de consultas")


API_ROUTER = APIRouter(prefix="/api/v1")
for _r in (health_router, auth_router, iam_router, audit_router, datasets_router, ingestion_router, dashboards_router,
           devices_router, display_router, settings_router, ai_router):
    API_ROUTER.include_router(_r)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging()
    broker.start()
    stop = asyncio.Event()
    worker_task = None
    if s.run_worker_inprocess:
        from app.workers.runner import run_forever

        worker_task = asyncio.create_task(run_forever(stop))
    yield
    stop.set()
    if worker_task:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(worker_task, timeout=10)
    await broker.stop()
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Gamatermic Dash API", version="0.1.0", lifespan=lifespan,
        docs_url="/api/docs" if s.docs_enabled else None, redoc_url=None,
        openapi_url="/api/openapi.json" if s.docs_enabled else None,
    )
    install_handlers(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "If-Match", "If-None-Match", "Idempotency-Key", "X-Requested-With"],
        expose_headers=["ETag", "Retry-After"],
    )

    @app.middleware("http")
    async def request_ctx(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid, path=request.url.path)
        t0 = time.perf_counter()
        is_sse = request.url.path.endswith("/display/stream")
        if is_sse:
            SSE_CONNS.inc()
        try:
            response: Response = await call_next(request)
        finally:
            if is_sse:
                SSE_CONNS.dec()
        dt = time.perf_counter() - t0
        route = request.scope.get("route")
        label = getattr(route, "path", "unmatched")
        HTTP_REQS.labels(request.method, label, str(response.status_code)).inc()
        if not is_sse:
            HTTP_LAT.labels(label).observe(dt)
            log.info("request", method=request.method, status=response.status_code, ms=round(dt * 1000, 1))
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.url.path.startswith("/api/v1/auth") or request.url.path.startswith("/api/v1/device"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(API_ROUTER)

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        # exposto apenas na rede interna (Caddy nao faz proxy de /metrics)
        CACHE_HITS.set(executor.STATS["hits"])
        CACHE_MISSES.set(executor.STATS["misses"])
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
