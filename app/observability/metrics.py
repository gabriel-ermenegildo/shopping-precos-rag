"""Métricas Prometheus expostas em GET /metrics."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "rag_http_requests_total", "Total de requests HTTP", ["route", "status"]
)
HTTP_LATENCY = Histogram(
    "rag_http_latency_seconds", "Latência por rota", ["route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
RETRIEVED_CHUNKS = Histogram(
    "rag_retrieved_chunks", "Chunks recuperados por pergunta",
    buckets=(0, 1, 2, 3, 5, 8, 13, 21),
)
FALLBACK_ANSWERS = Counter(
    "rag_fallback_answers_total", "Respostas 'não encontrei na documentação'"
)
LLM_LATENCY = Histogram(
    "rag_llm_latency_seconds", "Latência das chamadas ao LLM",
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32),
)
INDEXED_CHUNKS = Gauge("rag_indexed_chunks", "Chunks atualmente indexados")
INGEST_PAGES = Counter("rag_ingest_pages_total", "Páginas processadas na ingestão", ["result"])
