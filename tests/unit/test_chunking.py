"""Chunking semântico (RF03): código nunca dividido, overlap, breadcrumbs."""

from app.rag.chunking import SemanticChunker, count_tokens, split_blocks

CODE = "```bash\n" + "\n".join(f"linha de comando numero {i}" for i in range(80)) + "\n```"
DOC = (
    "# Endpoint de estoque\n\n"
    "Texto introdutório sobre o endpoint. " * 30 + "\n\n"
    "## Exemplo\n\n" + CODE + "\n\n"
    "Texto final explicando a resposta. " * 30
)


def test_split_blocks_marks_code():
    kinds = [b.kind for b in split_blocks(DOC)]
    assert "code" in kinds and "heading" in kinds and "text" in kinds


def test_code_block_never_split():
    chunker = SemanticChunker(chunk_size=300, chunk_overlap=50)
    chunks = chunker.chunk(DOC, {"url": "u", "title": "Endpoint de estoque"})
    with_code = [c for c in chunks if "```bash" in c.text]
    assert with_code, "bloco de código sumiu"
    for c in with_code:
        assert c.text.count("```") % 2 == 0, "cerca de código quebrada"
        assert "linha de comando numero 0" in c.text
        assert "linha de comando numero 79" in c.text


def test_chunks_respect_size_budget_for_text():
    chunker = SemanticChunker(chunk_size=300, chunk_overlap=50)
    chunks = chunker.chunk(DOC, {"url": "u", "title": "t"})
    only_text = [c for c in chunks if "```" not in c.text]
    assert only_text
    for c in only_text:
        assert count_tokens(c.text) <= 300 + 120  # margem p/ breadcrumb/overlap


def test_breadcrumb_prefix_and_metadata():
    chunker = SemanticChunker(chunk_size=300, chunk_overlap=50)
    chunks = chunker.chunk(DOC, {"url": "u", "title": "Endpoint de estoque"})
    assert all(c.text.startswith("[Contexto:") for c in chunks)
    assert all("chunk_index" in c.metadata and "section_path" in c.metadata for c in chunks)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), "ids de chunk repetidos"
