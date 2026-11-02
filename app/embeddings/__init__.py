"""Vetorização (RF04): camada abstrata de embeddings com múltiplos providers.

Providers (EMBEDDING_PROVIDER no .env):
  * openai               -> text-embedding-3-small / -3-large
  * sentence-transformers-> BGE, E5, Instructor etc. (local, open source)
                            default multilíngue p/ PT-BR: intfloat/multilingual-e5-small
  * fake                 -> determinístico, sem rede (testes/CI/demo offline;
                            o retrieval híbrido segue útil via BM25)

Detalhe que importa para qualidade: modelos E5 exigem prefixos
"query: " / "passage: ", e BGE recomenda instrução na query — tratados aqui
no adapter, de forma transparente para o resto do sistema.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from app.config.settings import Settings


class EmbeddingProvider(ABC):
    dimension: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbeddings(EmbeddingProvider):
    """Hash determinístico -> vetor unitário. Zero dependências, zero rede."""

    def __init__(self, dimension: int = 64):
        self.dimension = dimension

    def _one(self, text: str) -> list[float]:
        vec: list[float] = []
        i = 0
        while len(vec) < self.dimension:
            h = hashlib.sha256(f"{i}:{text}".encode()).digest()
            vec.extend(b / 255.0 - 0.5 for b in h)
            i += 1
        vec = vec[: self.dimension]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts):
        return [self._one(t) for t in texts]

    def embed_query(self, text):
        return self._one(text)


class OpenAIEmbeddings(EmbeddingProvider):
    _DIMS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}

    def __init__(self, model: str, api_key: str):
        from openai import OpenAI  # lazy import

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY ausente para EMBEDDING_PROVIDER=openai")
        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.dimension = self._DIMS.get(model, 1536)

    def embed_documents(self, texts):
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class SentenceTransformersEmbeddings(EmbeddingProvider):
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # lazy import

        self._model = SentenceTransformer(model)
        self.model = model
        self.dimension = self._model.get_sentence_embedding_dimension()
        name = model.lower()
        self._doc_prefix = "passage: " if "e5" in name else ""
        self._query_prefix = (
            "query: " if "e5" in name
            else "Represent this sentence for searching relevant passages: "
            if "bge" in name and "m3" not in name
            else ""
        )

    def embed_documents(self, texts):
        prepared = [self._doc_prefix + t for t in texts]
        return self._model.encode(prepared, normalize_embeddings=True,
                                  show_progress_bar=False).tolist()

    def embed_query(self, text):
        return self._model.encode([self._query_prefix + text],
                                  normalize_embeddings=True,
                                  show_progress_bar=False)[0].tolist()


def create_embedder(settings: Settings) -> EmbeddingProvider:
    p = settings.embedding_provider
    if p == "fake":
        return FakeEmbeddings()
    if p == "openai":
        return OpenAIEmbeddings(settings.openai_embedding_model, settings.openai_api_key)
    if p == "sentence-transformers":
        return SentenceTransformersEmbeddings(settings.embedding_model)
    raise ValueError(f"EMBEDDING_PROVIDER desconhecido: {p}")
