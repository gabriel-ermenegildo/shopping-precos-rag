"""Hybrid Search: fusão vetorial + BM25 via Reciprocal Rank Fusion (RRF).

RRF é robusto porque ignora escalas de score incompatíveis (cosseno vs BM25)
e usa apenas a POSIÇÃO de cada documento em cada ranking:
    score(d) = soma_r 1 / (rrf_k + rank_r(d))
"""

from __future__ import annotations

from app.retrieval.base import Retriever, ScoredChunk


def rrf_fuse(rankings: list[list[ScoredChunk]], rrf_k: int = 60) -> list[ScoredChunk]:
    fused: dict[str, float] = {}
    best: dict[str, ScoredChunk] = {}
    for ranking in rankings:
        for rank, sc in enumerate(ranking):
            cid = sc.chunk.id
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
            prev = best.get(cid)
            if prev is None or (sc.similarity or -1) > (prev.similarity or -1):
                best[cid] = sc
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [
        ScoredChunk(chunk=best[cid].chunk, score=score,
                    similarity=best[cid].similarity)
        for cid, score in ordered
    ]


class HybridRetriever(Retriever):
    def __init__(self, vector: Retriever, bm25: Retriever,
                 fetch_k: int = 20, rrf_k: int = 60):
        self.vector = vector
        self.bm25 = bm25
        self.fetch_k = fetch_k
        self.rrf_k = rrf_k

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        fused = rrf_fuse(
            [self.vector.retrieve(query, self.fetch_k),
             self.bm25.retrieve(query, self.fetch_k)],
            rrf_k=self.rrf_k,
        )
        return fused[:k]

    def refresh(self) -> None:
        self.vector.refresh()
        self.bm25.refresh()
