"""Cadeia RAG: grounding, fontes programáticas e fallback exato."""

from app.rag.prompts import FALLBACK_ANSWER


def test_answer_includes_sources_block(seeded_container):
    chain = seeded_container.get_chain()
    res = chain.answer("Como autenticar na API do Shopping de Preços?", session_id="t1")
    assert not res.used_fallback
    assert "Fontes:" in res.answer
    assert res.sources and all(s.url.startswith("https://") for s in res.sources)
    assert 0.0 <= res.confidence <= 1.0


def test_fallback_exact_phrase_when_index_empty(fresh_container):
    chain = fresh_container.get_chain()
    res = chain.answer("Como autenticar na API?", session_id="t2")
    assert res.used_fallback
    assert res.answer == FALLBACK_ANSWER
    assert res.sources == []


def test_memory_keeps_history(seeded_container):
    chain = seeded_container.get_chain()
    chain.answer("Como atualizar estoque?", session_id="mem")
    hist = seeded_container.get_memory().get("mem")
    assert len(hist) == 2 and hist[0]["role"] == "user"
