"""Rotas da API (RNF04).

POST /auth/token  -> emite JWT (credenciais do .env)
POST /chat        -> pergunta -> resposta com fontes (auth opcional via .env)
POST /ingest      -> ingestão incremental (SEMPRE autenticada)
POST /reindex     -> reindexação total (SEMPRE autenticada)
GET  /health      -> status + configuração ativa
GET  /metrics     -> Prometheus (montado em app/main.py)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app import __version__
from app.api import security
from app.api.schemas import (
    ChatRequest, ChatResponse, HealthResponse, IngestRequest, IngestResponse,
    SourceOut, TokenRequest, TokenResponse,
)
from app.config.settings import Settings, get_settings
from app.container import get_chain, get_pipeline, get_store, refresh_after_ingest
from app.observability.logging import log_extra

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/token", response_model=TokenResponse, tags=["auth"])
def issue_token(body: TokenRequest, settings: Settings = Depends(get_settings)):
    if not security.check_credentials(body.username, body.password, settings):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais inválidas")
    return TokenResponse(
        access_token=security.create_access_token(body.username, settings),
        expires_in_minutes=settings.jwt_expire_minutes,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["rag"],
    dependencies=[Depends(security.rate_limit)],
)
def chat(
    body: ChatRequest,
    _user: dict | None = Depends(security.optional_auth),
    settings: Settings = Depends(get_settings),
):
    question = security.sanitize_question(body.question, settings.max_question_chars)
    if settings.block_prompt_injection and security.detect_prompt_injection(question):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Pergunta rejeitada pelas regras de segurança")

    result = get_chain().answer(question, session_id=body.session_id, mode=body.mode)
    logger.info(
        "chat respondido",
        extra=log_extra(session=body.session_id, mode=body.mode,
                        fallback=result.used_fallback, latency_ms=result.latency_ms,
                        n_sources=len(result.sources)),
    )
    return ChatResponse(
        answer=result.answer,
        sources=[SourceOut(**s.__dict__) for s in result.sources],
        confidence=result.confidence,
        latency_ms=result.latency_ms,
        used_fallback=result.used_fallback,
        session_id=body.session_id,
    )


@router.post(
    "/ingest",
    response_model=IngestResponse,
    tags=["ingestion"],
    dependencies=[Depends(security.require_auth)],
)
def ingest(body: IngestRequest):
    stats = get_pipeline().run(full=body.full)
    refresh_after_ingest()
    return IngestResponse(**stats.as_dict())


@router.post(
    "/reindex",
    response_model=IngestResponse,
    tags=["ingestion"],
    dependencies=[Depends(security.require_auth)],
)
def reindex():
    """Atalho para ingestão FULL (limpa e reconstrói o índice)."""
    stats = get_pipeline().run(full=True)
    refresh_after_ingest()
    return IngestResponse(**stats.as_dict())


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health(settings: Settings = Depends(get_settings)):
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        vector_backend=settings.vector_backend,
        embedding_provider=settings.embedding_provider,
        llm_provider=settings.llm_provider,
        indexed_chunks=get_store().count(),
        version=__version__,
    )
