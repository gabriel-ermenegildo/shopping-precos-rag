"""Similarity search vetorial, com MMR opcional para diversidade."""

from __future__ import annotations

from app.config.settings import Settings
from app.embeddings import EmbeddingProvider
from app.retrieval.base import Retriever, ScoredChunk
from app.retrieval.mmr import mmr_select
from app.vectorstore.base import VectorStoreBase


class VectorRetriever(Retriever):
    def __init__(self, store: VectorStoreBase, embedder: EmbeddingProvider,
                 settings: Settings):
        self.store = store
        self.embedder = embedder
        self.s = settings

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        qvec = self.embedder.embed_query(query)
        fetch_k = max(k, self.s.fetch_k) if self.s.use_mmr else k
        results = self.store.search(qvec, fetch_k)
        results = [r for r in results if r.score >= self.s.score_threshold]

        if self.s.use_mmr and len(results) > k:
            with_vec = [r for r in results if r.embedding is not None]
            if len(with_vec) > k:
                chosen = mmr_select(
                    qvec, [r.embedding for r in with_vec], k, self.s.mmr_lambda
                )
                results = [with_vec[i] for i in chosen]
        return [ScoredChunk(chunk=r.chunk, score=r.score, similarity=r.score)
                for r in results[:k]]
