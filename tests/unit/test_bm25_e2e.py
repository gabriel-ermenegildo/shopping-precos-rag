"""BM25 sobre o store populado: busca lexical real em PT-BR."""


def test_bm25_finds_stock_endpoint(seeded_container):
    from app.retrieval.bm25_retriever import BM25Retriever

    retriever = BM25Retriever(seeded_container.get_store())
    retriever.refresh()
    results = retriever.retrieve("como atualizar estoque do produto", k=3)
    assert results
    top_urls = [r.chunk.metadata["url"] for r in results]
    assert any("atualiza-estoque-produto" in u for u in top_urls)
