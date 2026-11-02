"""Avaliação de qualidade do RAG (RNF07) com RAGAS.

Métricas: faithfulness, answer_relevancy, context_precision, context_recall.
RAGAS usa um LLM como juiz — exige OPENAI_API_KEY (ou LLM configurado no RAGAS).

Sem `ragas` instalado (é dependência opcional/pesada), run_evaluation() faz um
*smoke test*: roda as perguntas do golden dataset pela cadeia e reporta
cobertura de tópicos esperados + taxa de fallback. Útil em CI leve.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.container import get_chain

logger = logging.getLogger(__name__)
GOLDEN_PATH = Path(__file__).parent / "golden_dataset.json"


def load_golden() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["questions"]


def collect_runs() -> list[dict]:
    """Executa cada pergunta dourada pela cadeia e coleta pergunta/contexto/resposta."""
    chain = get_chain()
    runs = []
    for item in load_golden():
        res = chain.answer(item["question"], session_id=f"eval-{item['id']}")
        ctxs = [s.title + " " + s.url for s in res.sources]
        runs.append(
            {
                "id": item["id"],
                "question": item["question"],
                "answer": res.answer,
                "contexts": ctxs,
                "expected_topics": item.get("expected_topics", []),
                "used_fallback": res.used_fallback,
                "confidence": res.confidence,
            }
        )
    return runs


def smoke_report(runs: list[dict]) -> dict:
    total = len(runs)
    fallbacks = sum(r["used_fallback"] for r in runs)
    topic_hits = []
    for r in runs:
        text = (r["answer"] + " " + " ".join(r["contexts"])).lower()
        topics = r["expected_topics"]
        hit = sum(1 for t in topics if t.lower() in text)
        topic_hits.append(hit / len(topics) if topics else 1.0)
    return {
        "questions": total,
        "fallback_rate": round(fallbacks / total, 3) if total else 0.0,
        "avg_topic_coverage": round(sum(topic_hits) / total, 3) if total else 0.0,
        "per_question": [
            {"id": r["id"], "fallback": r["used_fallback"],
             "confidence": r["confidence"]} for r in runs
        ],
    }


def run_evaluation(use_ragas: bool = True) -> dict:
    runs = collect_runs()
    report: dict = {"smoke": smoke_report(runs)}

    if not use_ragas:
        return report
    try:
        from datasets import Dataset  # noqa: F401  (lazy)
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy, context_precision, context_recall, faithfulness,
        )
    except ImportError:
        logger.warning("pacote 'ragas' não instalado — retornando apenas smoke test. "
                       "Instale com: pip install ragas datasets")
        return report

    from datasets import Dataset

    ds = Dataset.from_list(
        [
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"] or ["(vazio)"],
                # ground_truth aproximado pelos tópicos esperados:
                "ground_truth": "; ".join(r["expected_topics"]) or r["question"],
            }
            for r in runs
        ]
    )
    result = evaluate(
        ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall]
    )
    report["ragas"] = {k: round(float(v), 4) for k, v in result.items()}
    return report
