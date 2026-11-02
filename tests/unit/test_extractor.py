"""Extração HTML→Markdown: poda de sidebar, código fenced, updated_at, título."""

from tests.conftest import APIDOC_HTML
from app.ingestion.extractor import html_to_markdown

URL = "https://apidoc.shoppingdeprecos.com.br/atualiza-estoque-produto"


def test_sidebar_links_are_pruned():
    doc = html_to_markdown(APIDOC_HTML, URL)
    assert "Lista integrações" not in doc.markdown  # sidebar removida
    assert "atualizaEstoqueProduto" in doc.markdown  # conteúdo preservado


def test_title_cleans_apidog_suffix():
    doc = html_to_markdown(APIDOC_HTML, URL)
    assert doc.title == "Atualiza estoque do produto"


def test_updated_at_captured():
    doc = html_to_markdown(APIDOC_HTML, URL)
    assert doc.updated_at and doc.updated_at.startswith("2026-02-18")


def test_code_blocks_become_fenced():
    doc = html_to_markdown(APIDOC_HTML, URL)
    assert "```bash" in doc.markdown and "```json" in doc.markdown
    assert doc.markdown.count("```") % 2 == 0
