"""Fábrica de banco vetorial — único ponto onde o backend concreto é escolhido."""

from app.config.settings import Settings
from app.vectorstore.base import InMemoryVectorStore, VectorStoreBase


def create_vector_store(settings: Settings) -> VectorStoreBase:
    backend = settings.vector_backend
    if backend == "memory":
        return InMemoryVectorStore()
    if backend == "chroma":
        from app.vectorstore.chroma_store import ChromaVectorStore

        return ChromaVectorStore(settings.chroma_dir, settings.collection_name)
    if backend == "faiss":
        from app.vectorstore.faiss_store import FaissVectorStore

        return FaissVectorStore(settings.faiss_dir, settings.collection_name)
    if backend == "qdrant":
        from app.vectorstore.qdrant_store import QdrantVectorStore

        return QdrantVectorStore(settings.qdrant_url, settings.qdrant_api_key,
                                 settings.collection_name)
    raise ValueError(f"VECTOR_BACKEND desconhecido: {backend}")
