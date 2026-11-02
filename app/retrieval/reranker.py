"""Re-ranking (RF06): cross-encoder BGE local ou Cohere Rerank via API.

Ambos são OPCIONAIS (USE_RERANKER=true) e carregados lazy — o sistema
funciona sem nenhum deles instalado.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.config.settings import Settings
from app.retrieval.base import ScoredChunk

logger = logging.getLogger(__name__)


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[ScoredChunk],
               top_n: int) -> list[ScoredChunk]: ...


class BGEReranker(Reranker):
    def __init__(self, model: str):
        from sentence_transformers import CrossEncoder  # lazy import

        self._model = CrossEncoder(model)

    def rerank(self, query, candidates, top_n):
        if not candidates:
            return []
        scores = self._model.predict([(query, c.chunk.text) for c in candidates])
        order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
        return [
            ScoredChunk(chunk=candidates[i].chunk, score=float(scores[i]),
                        similarity=candidates[i].similarity)
            for i in order[:top_n]
        ]


class CohereReranker(Reranker):
    def __init__(self, api_key: str, model: str = "rerank-multilingual-v3.0"):
        import cohere  # lazy import

        self._client = cohere.ClientV2(api_key=api_key)
        self._model = model

    def rerank(self, query, candidates, top_n):
        if not candidates:
            return []
        resp = self._client.rerank(
            model=self._model, query=query,
            documents=[c.chunk.text for c in candidates], top_n=top_n,
        )
        return [
            ScoredChunk(chunk=candidates[r.index].chunk,
                        score=float(r.relevance_score),
                        similarity=candidates[r.index].similarity)
            for r in resp.results
        ]


def create_reranker(settings: Settings) -> Reranker | None:
    if not settings.use_reranker:
        return None
    try:
        if settings.reranker_provider == "cohere":
            return CohereReranker(settings.cohere_api_key)
        return BGEReranker(settings.reranker_model)
    except ImportError as exc:
        logger.warning("Re-ranker indisponível (%s); seguindo sem re-rank.", exc)
        return None
