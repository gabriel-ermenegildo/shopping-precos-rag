"""Pipeline de ingestão (RF01 + RF02 + RNF08): crawl → extract → enrich → chunk → embed → upsert.

Indexação incremental via manifest (data/manifest.json):
  - guarda content_hash por URL; se a página não mudou, é pulada (skip)
  - se mudou, os chunks antigos da URL são removidos antes do upsert (sem lixo)
Versionamento simples: o HTML bruto de cada página é salvo em
data/raw/<sha16>.html, permitindo auditar o que foi indexado em cada execução.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import Settings
from app.embeddings import EmbeddingProvider
from app.ingestion.crawler import RawPage, crawl_all_sources
from app.ingestion.enricher import build_metadata
from app.ingestion.extractor import html_to_markdown
from app.observability.metrics import INDEXED_CHUNKS, INGEST_PAGES
from app.rag.chunking import SemanticChunker
from app.vectorstore.base import VectorStoreBase

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    pages_seen: int = 0
    pages_indexed: int = 0
    pages_skipped: int = 0
    pages_failed: int = 0
    chunks_indexed: int = 0
    started_at: str = ""
    finished_at: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__ | {"errors": self.errors[:20]}


class IngestionPipeline:
    def __init__(self, settings: Settings, store: VectorStoreBase, embedder: EmbeddingProvider):
        self.settings = settings
        self.store = store
        self.embedder = embedder
        self.chunker = SemanticChunker(settings.chunk_size, settings.chunk_overlap)
        self.manifest_path: Path = settings.data_dir / "manifest.json"

    # ------------------------------------------------------------ manifest
    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("manifest corrompido; recomeçando do zero")
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _snapshot_html(self, page: RawPage) -> None:
        sha = hashlib.sha256(page.html.encode("utf-8")).hexdigest()[:16]
        path = self.settings.data_dir / "raw" / f"{sha}.html"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page.html, encoding="utf-8")

    # ------------------------------------------------------------ execução
    def run(self, full: bool = False, pages: list[RawPage] | None = None) -> IngestStats:
        """full=True ignora o manifest (reindexa tudo). `pages` permite injetar
        páginas pré-baixadas (testes/fixtures) sem rede."""
        stats = IngestStats(started_at=datetime.now(timezone.utc).isoformat())
        manifest = {} if full else self._load_manifest()
        if full:
            logger.info("reindexação FULL: limpando coleção")
            self.store.clear()

        if pages is None:
            pages = asyncio.run(crawl_all_sources(self.settings))
        stats.pages_seen = len(pages)

        batch = max(1, self.settings.embedding_batch_size)
        for page in pages:
            try:
                doc = html_to_markdown(page.html, page.url)
                if not doc.markdown.strip():
                    stats.pages_skipped += 1
                    INGEST_PAGES.labels(result="empty").inc()
                    continue

                meta = build_metadata(page, doc)
                prev = manifest.get(page.url, {})
                if prev.get("content_hash") == meta["content_hash"]:
                    stats.pages_skipped += 1
                    INGEST_PAGES.labels(result="unchanged").inc()
                    continue

                self._snapshot_html(page)
                self.store.delete_by_url(page.url)  # remove versão antiga

                chunks = self.chunker.chunk(doc.markdown, meta)
                for i in range(0, len(chunks), batch):
                    part = chunks[i : i + batch]
                    embs = self.embedder.embed_documents([c.text for c in part])
                    self.store.upsert(part, embs)

                manifest[page.url] = {
                    "content_hash": meta["content_hash"],
                    "title": meta["title"],
                    "chunks": len(chunks),
                    "indexed_at": meta["indexed_at"],
                }
                stats.pages_indexed += 1
                stats.chunks_indexed += len(chunks)
                INGEST_PAGES.labels(result="indexed").inc()
            except Exception as exc:  # página ruim não derruba a ingestão
                stats.pages_failed += 1
                stats.errors.append(f"{page.url}: {exc}")
                INGEST_PAGES.labels(result="failed").inc()
                logger.exception("falha ao processar %s", page.url)

        self._save_manifest(manifest)
        INDEXED_CHUNKS.set(self.store.count())
        stats.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "ingestão concluída: %s indexadas, %s sem mudança, %s falhas, %s chunks",
            stats.pages_indexed, stats.pages_skipped, stats.pages_failed, stats.chunks_indexed,
        )
        return stats
