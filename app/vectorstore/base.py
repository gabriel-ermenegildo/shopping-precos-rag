"""Banco vetorial (RF05): contrato único, múltiplos backends.

A lógica de negócio (retrieval, pipeline) só conhece esta interface.
Trocar Chroma -> Qdrant em produção = VECTOR_BACKEND=qdrant no .env.

Backends:
  * memory  -> referência/testes (este arquivo)
  * chroma  -> local com persistência (default recomendado p/ dev)
  * faiss   -> local, alta performance de leitura
  * qdrant  -> produção (gerenciado ou self-hosted)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.rag.chunking import Chunk


@dataclass
class SearchResult:
    id: str
    text: str
    metadata: dict
    score: float                      # similaridade (maior = melhor)
    embedding: list[float] | None = field(default=None, repr=False)

    @property
    def chunk(self) -> Chunk:
        return Chunk(id=self.id, text=self.text, metadata=self.metadata)


class VectorStoreBase(ABC):
    @abstractmethod
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def search(self, query_embedding: list[float], k: int) -> list[SearchResult]: ...

    @abstractmethod
    def delete_by_url(self, url: str) -> int: ...

    @abstractmethod
    def dump_all(self) -> list[tuple[str, str, dict]]:
        """(id, text, metadata) de todos os chunks — usado para construir o BM25."""

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def clear(self) -> None: ...


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return num / (na * nb)


class InMemoryVectorStore(VectorStoreBase):
    """Implementação de referência: simples, correta, sem dependências."""

    def __init__(self):
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._vecs: list[list[float]] = []
        self._pos: dict[str, int] = {}

    def upsert(self, chunks, embeddings):
        for chunk, vec in zip(chunks, embeddings):
            if chunk.id in self._pos:
                i = self._pos[chunk.id]
                self._texts[i], self._metas[i], self._vecs[i] = chunk.text, chunk.metadata, vec
            else:
                self._pos[chunk.id] = len(self._ids)
                self._ids.append(chunk.id)
                self._texts.append(chunk.text)
                self._metas.append(chunk.metadata)
                self._vecs.append(vec)

    def search(self, query_embedding, k):
        scored = sorted(
            range(len(self._ids)),
            key=lambda i: cosine(query_embedding, self._vecs[i]),
            reverse=True,
        )[:k]
        return [
            SearchResult(
                id=self._ids[i], text=self._texts[i], metadata=self._metas[i],
                score=cosine(query_embedding, self._vecs[i]), embedding=self._vecs[i],
            )
            for i in scored
        ]

    def delete_by_url(self, url):
        keep = [i for i, m in enumerate(self._metas) if m.get("url") != url]
        removed = len(self._ids) - len(keep)
        self._ids = [self._ids[i] for i in keep]
        self._texts = [self._texts[i] for i in keep]
        self._metas = [self._metas[i] for i in keep]
        self._vecs = [self._vecs[i] for i in keep]
        self._pos = {cid: i for i, cid in enumerate(self._ids)}
        return removed

    def dump_all(self):
        return list(zip(self._ids, self._texts, self._metas))

    def count(self):
        return len(self._ids)

    def clear(self):
        self.__init__()
