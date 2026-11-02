"""Cadeia RAG (RF06–RF12): orquestra retrieval, geração, fontes e memória.

Fluxo de answer():
  1. (opcional) condensa follow-up usando o histórico (RF11)
  2. retrieval (vector | bm25 | hybrid) com fetch_k candidatos
  3. modo agente (RF12): LLM pode pedir até N buscas extras; resultados são
     fundidos por id (multi-document retrieval)
  4. (opcional) re-ranking BGE/Cohere (RF06)
  5. compressão de contexto: dedupe + corte por orçamento de tokens
  6. geração com grounding (RF08) — se nada foi recuperado, fallback direto
  7. bloco "Fontes:" (RF09) montado PROGRAMATICAMENTE (não confiamos no LLM)
  8. score de confiança = melhor similaridade vetorial disponível
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from app.config.settings import Settings
from app.generation.base import LLMProvider, Message
from app.generation.memory import ConversationMemory
from app.observability.metrics import FALLBACK_ANSWERS, LLM_LATENCY, RETRIEVED_CHUNKS
from app.rag.chunking import count_tokens
from app.rag.prompts import (
    AGENT_PLAN_PROMPT,
    CONDENSE_PROMPT,
    FALLBACK_ANSWER,
    SYSTEM_PROMPT,
    build_context_block,
)
from app.retrieval.base import Retriever, ScoredChunk
from app.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass
class SourceRef:
    index: int
    title: str
    url: str
    score: float


@dataclass
class AnswerResult:
    answer: str
    sources: list[SourceRef] = field(default_factory=list)
    confidence: float = 0.0
    latency_ms: int = 0
    used_fallback: bool = False


def _merge_by_id(*lists: list[ScoredChunk]) -> list[ScoredChunk]:
    """Funde listas de candidatos preservando o melhor score por chunk."""
    best: dict[str, ScoredChunk] = {}
    for lst in lists:
        for sc in lst:
            cur = best.get(sc.chunk.id)
            if cur is None or sc.score > cur.score:
                best[sc.chunk.id] = sc
    return sorted(best.values(), key=lambda s: s.score, reverse=True)


class RAGChain:
    def __init__(
        self,
        retriever: Retriever,
        llm: LLMProvider,
        memory: ConversationMemory,
        settings: Settings,
        reranker: Reranker | None = None,
    ):
        self.retriever = retriever
        self.llm = llm
        self.memory = memory
        self.settings = settings
        self.reranker = reranker

    # ------------------------------------------------------------ etapas
    def _condense(self, question: str, history: list[Message]) -> str:
        if not history or not self.settings.enable_condense:
            return question
        hist_txt = "\n".join(
            f"{'Usuário' if m['role'] == 'user' else 'Assistente'}: {m['content'][:400]}"
            for m in history[-6:]
        )
        prompt = CONDENSE_PROMPT.format(history=hist_txt, question=question)
        try:
            rewritten = self.llm.chat([{"role": "user", "content": prompt}]).strip()
            # sanidade: se o LLM devolveu algo vazio ou gigante, mantém original
            if 0 < len(rewritten) <= 4 * len(question) + 200:
                return rewritten
        except Exception:
            logger.warning("condense falhou; usando pergunta original", exc_info=True)
        return question

    def _agent_extra_queries(self, question: str, candidates: list[ScoredChunk]) -> list[str]:
        max_q = self.settings.agent_max_extra_queries
        if max_q <= 0:
            return []
        titles = "; ".join(
            dict.fromkeys(c.chunk.metadata.get("title", "") for c in candidates[:8])
        )
        prompt = AGENT_PLAN_PROMPT.format(question=question, titles=titles, max_queries=max_q)
        try:
            raw = self.llm.chat([{"role": "user", "content": prompt}])
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                return []
            data = json.loads(m.group(0))
            queries = [q.strip() for q in data.get("buscas_adicionais", []) if isinstance(q, str)]
            return queries[:max_q]
        except Exception:
            logger.debug("plano do agente ilegível; seguindo sem buscas extras")
            return []

    def _retrieve(self, question: str, mode: str) -> list[ScoredChunk]:
        k = max(self.settings.fetch_k, self.settings.top_k)
        candidates = self.retriever.retrieve(question, k)

        if mode == "agent" and candidates:
            for extra in self._agent_extra_queries(question, candidates):
                logger.info("modo agente: busca extra '%s'", extra)
                candidates = _merge_by_id(candidates, self.retriever.retrieve(extra, k))

        if self.reranker and candidates:
            candidates = self.reranker.rerank(question, candidates, self.settings.top_k)
        return candidates[: self.settings.top_k]

    def _compress_context(self, chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        """Dedupe textual + corte por orçamento de tokens, preservando ordem."""
        budget = self.settings.max_context_tokens
        seen_hash: set[str] = set()
        kept: list[ScoredChunk] = []
        used = 0
        for sc in chunks:
            key = sc.chunk.text[:160]
            if key in seen_hash:
                continue
            seen_hash.add(key)
            cost = count_tokens(sc.chunk.text)
            if kept and used + cost > budget:
                break  # mantém ao menos 1 chunk mesmo que estoure
            kept.append(sc)
            used += cost
        return kept

    # ------------------------------------------------------------ público
    def answer(self, question: str, session_id: str = "default", mode: str = "chat") -> AnswerResult:
        t0 = time.perf_counter()
        history = self.memory.get(session_id)
        standalone = self._condense(question, history)

        chunks = self._compress_context(self._retrieve(standalone, mode))
        RETRIEVED_CHUNKS.observe(len(chunks))

        if not chunks:
            FALLBACK_ANSWERS.inc()
            self.memory.add(session_id, question, FALLBACK_ANSWER)
            return AnswerResult(
                answer=FALLBACK_ANSWER,
                used_fallback=True,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        docs, sources = [], []
        for i, sc in enumerate(chunks, start=1):
            md = sc.chunk.metadata
            docs.append(
                {"index": i, "title": md.get("title", "Documentação"),
                 "url": md.get("url", ""), "text": sc.chunk.text}
            )
            sources.append(
                SourceRef(index=i, title=md.get("title", "Documentação"),
                          url=md.get("url", ""), score=round(sc.similarity or sc.score, 4))
            )

        user_msg = (
            f"{build_context_block(docs)}\n\n"
            f"PERGUNTA: {standalone}\n\n"
            "Responda seguindo as regras do sistema, citando [n] as fontes usadas."
        )
        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += history
        messages.append({"role": "user", "content": user_msg})

        t_llm = time.perf_counter()
        answer_text = self.llm.chat(messages).strip()
        LLM_LATENCY.observe(time.perf_counter() - t_llm)

        used_fallback = FALLBACK_ANSWER in answer_text
        if used_fallback:
            FALLBACK_ANSWERS.inc()
            sources = []
        else:
            # RF09: bloco de fontes determinístico, com título + URL
            cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer_text)}
            shown = [s for s in sources if s.index in cited] or sources
            fontes = "\n".join(f"[{s.index}] {s.title}\n{s.url}" for s in shown)
            answer_text = f"{answer_text}\n\nFontes:\n{fontes}"
            sources = shown

        confidence = max((s.score for s in sources), default=0.0)
        self.memory.add(session_id, question, answer_text)
        return AnswerResult(
            answer=answer_text,
            sources=sources,
            confidence=round(min(max(confidence, 0.0), 1.0), 4),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            used_fallback=used_fallback,
        )
