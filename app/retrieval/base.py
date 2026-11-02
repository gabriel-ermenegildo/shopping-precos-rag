"""Contratos da camada de retrieval (RF06)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.rag.chunking import Chunk


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float                       # semântica depende da estratégia
    similarity: float | None = None    # similaridade vetorial bruta, se houver


class Retriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, k: int) -> list[ScoredChunk]: ...

    def refresh(self) -> None:
        """Reconstrói estado interno após (re)ingestão. Default: no-op."""
