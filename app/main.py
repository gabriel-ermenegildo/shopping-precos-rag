"""Aplicação FastAPI (entrypoint ASGI): `uvicorn app.main:app`.

- Middleware: request_id por requisição + métricas Prometheus de latência.
- GET /metrics: exposto via prometheus_client (make_asgi_app).
- Reindexação agendada (RF01): se REINDEX_INTERVAL_HOURS > 0, uma task de
  background roda a ingestão incremental nesse intervalo.
- OpenTelemetry: ativado se ENABLE_TRACING=true e extras instalados.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app import __version__
from app.api.routes import router
from app.config.settings import get_settings
from app.observability.logging import request_id_var, setup_logging
from app.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS
from app.observability.tracing import setup_tracing

logger = logging.getLogger(__name__)


async def _scheduled_reindex(interval_hours: float) -> None:
    from app.container import get_pipeline, refresh_after_ingest

    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            logger.info("reindexação agendada iniciando")
            stats = await asyncio.to_thread(get_pipeline().run, False)
            refresh_after_ingest()
            logger.info("reindexação agendada ok: %s páginas indexadas", stats.pages_indexed)
        except Exception:
            logger.exception("reindexação agendada falhou; tentará no próximo ciclo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    setup_tracing(app, settings)

    # reconstrói o BM25 a partir do que já existe no banco vetorial persistente
    from app.container import refresh_after_ingest
    try:
        refresh_after_ingest()
    except Exception:
        logger.warning("não foi possível pré-carregar índices; siga com /ingest")

    task = None
    if settings.reindex_interval_hours > 0:
        task = asyncio.create_task(_scheduled_reindex(settings.reindex_interval_hours))
        logger.info("reindex agendada a cada %.1fh", settings.reindex_interval_hours)
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Shopping de Preços — RAG API",
        description="Assistente RAG sobre a documentação oficial do Shopping de Preços",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        request_id_var.set(uuid.uuid4().hex[:12])
        route = request.url.path
        t0 = time.perf_counter()
        response = await call_next(request)
        if not route.startswith("/metrics"):
            HTTP_LATENCY.labels(route=route).observe(time.perf_counter() - t0)
            HTTP_REQUESTS.labels(route=route, status=str(response.status_code)).inc()
        response.headers["X-Request-ID"] = request_id_var.get()
        return response

    app.include_router(router)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()
