"""Backend Qdrant (produção). Coleção criada lazy na primeira ingestão."""

from __future__ import annotations

import uuid

from app.rag.chunking import Chunk
from app.vectorstore.base import SearchResult, VectorStoreBase


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantVectorStore(VectorStoreBase):
    def __init__(self, url: str, api_key: str, collection: str):
        from qdrant_client import QdrantClient  # lazy import

        self._client = QdrantClient(url=url, api_key=api_key or None)
        self._name = collection

    def _exists(self) -> bool:
        return self._client.collection_exists(self._name)

    def _ensure(self, dim: int):
        from qdrant_client.models import Distance, VectorParams

        if not self._exists():
            self._client.create_collection(
                self._name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def upsert(self, chunks: list[Chunk], embeddings):
        from qdrant_client.models import PointStruct

        if not chunks:
            return
        self._ensure(len(embeddings[0]))
        points = [
            PointStruct(
                id=_point_id(c.id),
                vector=vec,
                payload={"chunk_id": c.id, "text": c.text, **c.metadata},
            )
            for c, vec in zip(chunks, embeddings)
        ]
        self._client.upsert(self._name, points=points, wait=True)

    def search(self, query_embedding, k):
        if not self._exists():
            return []
        hits = self._client.query_points(
            self._name, query=query_embedding, limit=k, with_vectors=True
        ).points
        return [
            SearchResult(
                id=h.payload.get("chunk_id", str(h.id)),
                text=h.payload.get("text", ""),
                metadata={kk: vv for kk, vv in h.payload.items()
                          if kk not in ("text", "chunk_id")},
                score=float(h.score),
                embedding=list(h.vector) if h.vector else None,
            )
            for h in hits
        ]

    def delete_by_url(self, url):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if not self._exists():
            return 0
        before = self.count()
        self._client.delete(
            self._name,
            points_selector=Filter(must=[FieldCondition(key="url", match=MatchValue(value=url))]),
            wait=True,
        )
        return before - self.count()

    def dump_all(self):
        if not self._exists():
            return []
        out, offset = [], None
        while True:
            points, offset = self._client.scroll(
                self._name, limit=256, offset=offset, with_payload=True
            )
            for p in points:
                out.append((
                    p.payload.get("chunk_id", str(p.id)),
                    p.payload.get("text", ""),
                    {kk: vv for kk, vv in p.payload.items()
                     if kk not in ("text", "chunk_id")},
                ))
            if offset is None:
                break
        return out

    def count(self):
        if not self._exists():
            return 0
        return self._client.count(self._name, exact=True).count

    def clear(self):
        if self._exists():
            self._client.delete_collection(self._name)
