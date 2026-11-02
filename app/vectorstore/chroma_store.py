"""Backend ChromaDB (local com persistência) — recomendado para dev."""

from __future__ import annotations

from pathlib import Path

from app.rag.chunking import Chunk
from app.vectorstore.base import SearchResult, VectorStoreBase


class ChromaVectorStore(VectorStoreBase):
    def __init__(self, persist_dir: Path, collection: str):
        import chromadb  # lazy import

        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._name = collection
        self._col = self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks: list[Chunk], embeddings):
        if not chunks:
            return
        self._col.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[{k: v for k, v in c.metadata.items() if v is not None}
                       for c in chunks],
        )

    def search(self, query_embedding, k):
        if self.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=[query_embedding],
            n_results=min(k, self.count()),
            include=["documents", "metadatas", "distances", "embeddings"],
        )
        out = []
        embs = res.get("embeddings")
        for i, cid in enumerate(res["ids"][0]):
            emb = None
            if embs is not None and len(embs) and embs[0] is not None:
                emb = [float(x) for x in embs[0][i]]
            out.append(SearchResult(
                id=cid,
                text=res["documents"][0][i],
                metadata=res["metadatas"][0][i] or {},
                score=1.0 - float(res["distances"][0][i]),  # cosine dist -> sim
                embedding=emb,
            ))
        return out

    def delete_by_url(self, url):
        before = self.count()
        self._col.delete(where={"url": url})
        return before - self.count()

    def dump_all(self):
        out, offset, page = [], 0, 500
        while True:
            res = self._col.get(include=["documents", "metadatas"],
                                limit=page, offset=offset)
            ids = res.get("ids", [])
            if not ids:
                break
            for i, cid in enumerate(ids):
                out.append((cid, res["documents"][i], res["metadatas"][i] or {}))
            offset += len(ids)
            if len(ids) < page:
                break
        return out

    def count(self):
        return self._col.count()

    def clear(self):
        self._client.delete_collection(self._name)
        self._col = self._client.get_or_create_collection(
            self._name, metadata={"hnsw:space": "cosine"}
        )
