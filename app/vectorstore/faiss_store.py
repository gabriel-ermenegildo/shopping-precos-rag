"""Backend FAISS (IndexFlatIP sobre vetores normalizados = cosseno).

Persistência: índice binário + sidecar JSON com ids/textos/metadados.
delete_by_url reconstrói o índice (aceitável para corpora de documentação).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.chunking import Chunk
from app.vectorstore.base import SearchResult, VectorStoreBase


class FaissVectorStore(VectorStoreBase):
    def __init__(self, persist_dir: Path, collection: str):
        import faiss  # lazy import
        import numpy as np

        self._faiss, self._np = faiss, np
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = persist_dir / f"{collection}.faiss"
        self._meta_path = persist_dir / f"{collection}.json"
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._index = None
        self._load()

    # ------------------------------------------------------------ internals
    def _load(self):
        if self._index_path.exists() and self._meta_path.exists():
            self._index = self._faiss.read_index(str(self._index_path))
            data = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self._ids, self._texts, self._metas = data["ids"], data["texts"], data["metas"]

    def _persist(self):
        if self._index is not None:
            self._faiss.write_index(self._index, str(self._index_path))
        self._meta_path.write_text(json.dumps(
            {"ids": self._ids, "texts": self._texts, "metas": self._metas},
            ensure_ascii=False), encoding="utf-8")

    def _normalize(self, arr):
        norms = self._np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    # ------------------------------------------------------------------ api
    def upsert(self, chunks: list[Chunk], embeddings):
        if not chunks:
            return
        existing = set(self._ids)
        for url in {c.metadata.get("url") for c in chunks if c.id in existing}:
            if url:
                self.delete_by_url(url)
        arr = self._normalize(self._np.asarray(embeddings, dtype="float32"))
        if self._index is None:
            self._index = self._faiss.IndexFlatIP(arr.shape[1])
        self._index.add(arr)
        for c in chunks:
            self._ids.append(c.id)
            self._texts.append(c.text)
            self._metas.append(c.metadata)
        self._persist()

    def search(self, query_embedding, k):
        if self._index is None or self._index.ntotal == 0:
            return []
        q = self._normalize(self._np.asarray([query_embedding], dtype="float32"))
        scores, idx = self._index.search(q, min(k, self._index.ntotal))
        out = []
        for score, i in zip(scores[0], idx[0]):
            if i < 0:
                continue
            vec = self._index.reconstruct(int(i))
            out.append(SearchResult(
                id=self._ids[i], text=self._texts[i], metadata=self._metas[i],
                score=float(score), embedding=[float(x) for x in vec],
            ))
        return out

    def delete_by_url(self, url):
        keep = [i for i, m in enumerate(self._metas) if m.get("url") != url]
        removed = len(self._ids) - len(keep)
        if removed == 0:
            return 0
        vecs = self._np.asarray(
            [self._index.reconstruct(i) for i in keep], dtype="float32"
        ) if keep else None
        self._ids = [self._ids[i] for i in keep]
        self._texts = [self._texts[i] for i in keep]
        self._metas = [self._metas[i] for i in keep]
        if keep:
            self._index = self._faiss.IndexFlatIP(vecs.shape[1])
            self._index.add(vecs)
        else:
            self._index = None
        self._persist()
        return removed

    def dump_all(self):
        return list(zip(self._ids, self._texts, self._metas))

    def count(self):
        return len(self._ids)

    def clear(self):
        self._ids, self._texts, self._metas, self._index = [], [], [], None
        for p in (self._index_path, self._meta_path):
            p.unlink(missing_ok=True)
