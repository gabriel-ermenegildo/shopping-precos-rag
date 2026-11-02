"""Busca lexical BM25 (rank-bm25) sobre o conteúdo do banco vetorial.

Tokenização para PT-BR: minúsculas + remoção de acentos + regex de palavra. Índice em
memória, reconstruído via refresh() após cada ingestão.
"""

from __future__ import annotations

import re
import unicodedata

from rank_bm25 import BM25Okapi

from app.rag.chunking import Chunk
from app.retrieval.base import Retriever, ScoredChunk
from app.vectorstore.base import VectorStoreBase

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize_pt(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _TOKEN_RE.findall(text)


class BM25Retriever(Retriever):
    def __init__(self, store: VectorStoreBase):
        self.store = store
        self._bm25: BM25Okapi | None = None
        self._chunks: list[Chunk] = []
        self.refresh()

    def refresh(self) -> None:
        rows = self.store.dump_all()
        self._chunks = [Chunk(id=i, text=t, metadata=m) for i, t, m in rows]
        corpus = [tokenize_pt(c.text) for c in self._chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def retrieve(self, query: str, k: int) -> list[ScoredChunk]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize_pt(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [ScoredChunk(chunk=self._chunks[i], score=float(scores[i]))
                for i in order if scores[i] > 0]
