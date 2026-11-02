"""Schemas Pydantic da API (contratos de entrada/saída)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, description="Pergunta em linguagem natural")
    session_id: str = Field(default="default", max_length=128)
    mode: str = Field(default="chat", pattern="^(chat|agent)$")


class SourceOut(BaseModel):
    index: int
    title: str
    url: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut] = []
    confidence: float = 0.0
    latency_ms: int = 0
    used_fallback: bool = False
    session_id: str


class IngestRequest(BaseModel):
    full: bool = Field(default=False, description="True = reindexa tudo do zero")


class IngestResponse(BaseModel):
    pages_seen: int
    pages_indexed: int
    pages_skipped: int
    pages_failed: int
    chunks_indexed: int
    started_at: str
    finished_at: str
    errors: list[str] = []


class HealthResponse(BaseModel):
    status: str
    environment: str
    vector_backend: str
    embedding_provider: str
    llm_provider: str
    indexed_chunks: int
    version: str
