"""Enriquecimento de metadados (RF02): endpoint, método, categoria."""

from tests.conftest import APIDOC_HTML, make_pages
from app.ingestion.enricher import build_metadata
from app.ingestion.extractor import html_to_markdown


def test_metadata_fields_complete():
    page = make_pages()[0]
    doc = html_to_markdown(APIDOC_HTML, page.url)
    meta = build_metadata(page, doc)
    for key in ("source", "url", "title", "section", "endpoint", "method",
                "updated_at", "category", "content_hash", "indexed_at"):
        assert key in meta, f"faltou {key}"
    assert meta["method"] == "POST"
    assert meta["endpoint"].endswith("atualizaEstoqueProduto")
    assert meta["category"] == "estoque"
    assert meta["source"] == "apidoc"
