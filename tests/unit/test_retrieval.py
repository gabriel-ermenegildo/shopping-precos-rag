"""Retrieval (RF06): BM25, fusão RRF híbrida e MMR."""

from app.rag.chunking import Chunk
from app.retrieval.base import ScoredChunk
from app.retrieval.hybrid import rrf_fuse
from app.retrieval.mmr import mmr_select


def _sc(cid: str, score: float, sim: float | None = None) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(id=cid, text=cid, metadata={}), score=score, similarity=sim)


def test_rrf_prefers_chunks_present_in_both_rankings():
    vec = [_sc("a", 0.9, 0.9), _sc("b", 0.8, 0.8), _sc("c", 0.7, 0.7)]
    bm25 = [_sc("b", 12.0), _sc("d", 9.0), _sc("a", 5.0)]
    fused = rrf_fuse([vec, bm25], rrf_k=60)
    order = [s.chunk.id for s in fused]
    assert set(order[:2]) == {"a", "b"}      # presentes nos dois rankings
    assert order.index("b") < order.index("d")


def test_rrf_preserves_best_similarity():
    vec = [_sc("a", 0.9, 0.91)]
    bm25 = [_sc("a", 7.0)]
    fused = rrf_fuse([vec, bm25], rrf_k=60)
    assert fused[0].similarity == 0.91


def test_mmr_promotes_diversity():
    # b é duplicata exata de a; c é igualmente relevante mas diverso.
    # MMR deve escolher a (mais similar primeiro) e depois c, pulando a duplicata.
    q = [1.0, 0.0]
    vecs = [[0.95, 0.312], [0.95, 0.312], [0.95, -0.312]]  # a, b=dup(a), c
    chosen = mmr_select(q, vecs, k=2, lambda_=0.5)
    assert chosen == [0, 2]
