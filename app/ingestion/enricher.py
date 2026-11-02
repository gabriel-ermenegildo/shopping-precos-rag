"""Enriquecimento (RF02): metadados estruturados por documento.

Contrato de metadados (vai junto de cada chunk para o banco vetorial):
{
  "source": "helpcenter" | "apidoc",
  "url": "...",
  "title": "...",
  "section": "...",
  "endpoint": "https://api.shoppingdeprecos.com.br/...",   (quando aplicável)
  "method": "GET|POST|PUT|PATCH|DELETE",                    (quando aplicável)
  "updated_at": "ISO-8601",
  "category": "produtos|pedidos|...",
  "content_hash": "sha256 do markdown (detecção de mudanças)"
}
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.ingestion.crawler import RawPage
from app.ingestion.extractor import ExtractedDoc

# Padrão visto nas páginas Apidog: linha "POST" seguida da URL completa da API.
_ENDPOINT_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\b[\s:]+(`?)(https?://[^\s`'\"<>]+|/[A-Za-z0-9_\-./{}]+)\2",
    re.IGNORECASE,
)

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("pedidos", ("pedido", "etiqueta", "status-pedido", "aceite")),
    ("notas-fiscais", ("nfe", "nfs", "nota", "xml")),
    ("estoque", ("estoque",)),
    ("precos", ("preco", "preço")),
    ("produtos", ("produto", "schema", "modelo", "categoria", "marca", "atributo", "variac")),
    ("integracoes", ("integra", "plataforma", "marketplace", "erp")),
    ("autenticacao", ("introducao-a-api", "introducao", "token", "autentic")),
    ("concorrentes", ("concorrente", "vendedor")),
    ("configuracao", ("configura",)),
]


def _categorize(url: str, title: str) -> str:
    haystack = f"{urlparse(url).path} {title}".lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in haystack for n in needles):
            return category
    return "geral"


def build_metadata(page: RawPage, doc: ExtractedDoc) -> dict:
    method, endpoint = "", ""
    m = _ENDPOINT_RE.search(doc.markdown)
    if m:
        method, endpoint = m.group(1).upper(), m.group(3)

    section = doc.headings[0] if doc.headings else doc.title
    return {
        "source": page.source,
        "url": page.url,
        "title": doc.title,
        "section": section,
        "endpoint": endpoint,
        "method": method,
        "updated_at": doc.updated_at or page.fetched_at,
        "category": _categorize(page.url, doc.title),
        "content_hash": hashlib.sha256(doc.markdown.encode("utf-8")).hexdigest(),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
