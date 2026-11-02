"""Integração: API FastAPI + pipeline + banco vetorial (tudo offline)."""

from fastapi.testclient import TestClient

from app.ingestion.pipeline import IngestionPipeline
from app.main import create_app
from tests.conftest import make_pages

_original_run = IngestionPipeline.run


def _client() -> TestClient:
    return TestClient(create_app())


def test_health_ok(seeded_container):
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["vector_backend"] == "memory"
    assert body["indexed_chunks"] > 0


def test_chat_returns_schema_and_sources(seeded_container):
    with _client() as client:
        resp = client.post("/chat", json={
            "question": "Como atualizar o estoque de um produto?",
            "session_id": "it-1",
        })
    assert resp.status_code == 200
    body = resp.json()
    for key in ("answer", "sources", "confidence", "latency_ms",
                "used_fallback", "session_id"):
        assert key in body
    assert body["used_fallback"] is False
    assert body["sources"], "esperava fontes citadas"
    assert "Fontes:" in body["answer"]


def test_chat_rejects_empty_question(seeded_container):
    with _client() as client:
        resp = client.post("/chat", json={"question": "   ", "session_id": "x"})
    assert resp.status_code == 400


def test_ingest_requires_auth(fresh_container):
    with _client() as client:
        resp = client.post("/ingest", json={"full": True})
    assert resp.status_code == 401


def test_token_flow_and_protected_reindex(seeded_container, monkeypatch):
    # /reindex chamaria o crawler real; injetamos as fixtures no lugar da rede
    monkeypatch.setattr(
        IngestionPipeline, "run",
        lambda self, full=False, pages=None: _original_run(self, full=full, pages=make_pages()),
        raising=True,
    )

    with _client() as client:
        bad = client.post("/auth/token", json={"username": "admin", "password": "errada"})
        assert bad.status_code == 401

        ok = client.post("/auth/token", json={"username": "admin", "password": "admin"})
        assert ok.status_code == 200
        token = ok.json()["access_token"]

        no_token = client.post("/reindex")
        assert no_token.status_code == 401

        resp = client.post("/reindex", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["pages_indexed"] >= 1
