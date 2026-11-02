"""Composition root (Clean Architecture): único lugar que monta o grafo de objetos.

Rotas, scripts e testes pedem instâncias AQUI — nunca constroem adapters na mão.
Após (re)ingestão, refresh_after_ingest() reconstrói o índice BM25 em memória.
"""

from __future__ import annotations

from functools import lru_cache

from app.config.settings import Settings, get_settings
from app.embeddings import EmbeddingProvider, create_embedder
from app.generation.base import LLMProvider
from app.generation.memory import ConversationMemory
from app.generation.providers import create_llm
from app.ingestion.pipeline import IngestionPipeline
from app.rag.chain import RAGChain
from app.retrieval.base import Retriever
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import create_reranker
from app.retrieval.vector_retriever import VectorRetriever
from app.vectorstore.base import VectorStoreBase
from app.vectorstore.factory import create_vector_store


@lru_cache
def get_embedder() -> EmbeddingProvider:
    return create_embedder(get_settings())


@lru_cache
def get_store() -> VectorStoreBase:
    return create_vector_store(get_settings())


@lru_cache
def get_llm() -> LLMProvider:
    return create_llm(get_settings())


@lru_cache
def get_memory() -> ConversationMemory:
    return ConversationMemory(max_turns=get_settings().memory_max_turns)


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        s: Settings = get_settings()
        store, embedder = get_store(), get_embedder()
        vector = VectorRetriever(store, embedder, s)
        if s.retrieval_mode == "vector":
            _retriever = vector
        elif s.retrieval_mode == "bm25":
            _retriever = BM25Retriever(store)
        else:
            _retriever = HybridRetriever(vector, BM25Retriever(store), rrf_k=s.rrf_k)
    return _retriever


def get_pipeline() -> IngestionPipeline:
    return IngestionPipeline(get_settings(), get_store(), get_embedder())


@lru_cache
def get_chain() -> RAGChain:
    s = get_settings()
    return RAGChain(
        retriever=get_retriever(),
        llm=get_llm(),
        memory=get_memory(),
        settings=s,
        reranker=create_reranker(s),
    )


def refresh_after_ingest() -> None:
    """Reconstrói índices derivados (BM25) após nova ingestão."""
    get_retriever().refresh()


def reset_container() -> None:
    """Usado pelos testes para recomeçar com settings/env diferentes."""
    global _retriever
    _retriever = None
    for fn in (get_embedder, get_store, get_llm, get_memory, get_chain, get_settings):
        fn.cache_clear()
