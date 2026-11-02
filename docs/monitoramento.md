# Monitoramento e observabilidade

## Logs

JSON estruturado no stdout (parseável por Loki/CloudWatch/Datadog), com
`request_id` propagado por requisição:

```json
{"ts":"2026-06-12T12:00:00+00:00","level":"INFO","logger":"app.api.routes",
 "msg":"chat respondido","request_id":"a1b2c3d4e5f6","session":"abc",
 "mode":"chat","fallback":false,"latency_ms":1240,"n_sources":3}
```

## Métricas Prometheus (`GET /metrics`)

| Métrica | Tipo | Para quê |
|---|---|---|
| `rag_http_requests_total{route,status}` | counter | tráfego e taxa de erro |
| `rag_http_latency_seconds{route}` | histogram | p50/p95/p99 por rota |
| `rag_llm_latency_seconds` | histogram | custo de latência do LLM |
| `rag_retrieved_chunks` | histogram | saúde do retrieval |
| `rag_fallback_answers_total` | counter | lacunas de cobertura da doc |
| `rag_indexed_chunks` | gauge | tamanho do índice |
| `rag_ingest_pages_total{result}` | counter | indexed/unchanged/failed/empty |

Suba a stack local: `docker compose --profile observability up`
(Prometheus :9090, Grafana :3000, login admin/admin).

## Consultas úteis (PromQL)

```promql
# p95 do /chat
histogram_quantile(0.95, rate(rag_http_latency_seconds_bucket{route="/chat"}[5m]))

# taxa de fallback (proxy de qualidade)
rate(rag_fallback_answers_total[1h]) / rate(rag_http_requests_total{route="/chat"}[1h])

# erros 5xx
sum(rate(rag_http_requests_total{status=~"5.."}[5m]))
```

## Alertas sugeridos

- p95 `/chat` > 8s por 10 min → degradação do LLM/retrieval
- taxa de fallback > 30% por 1h → doc desatualizada ou índice quebrado
- `rag_ingest_pages_total{result="failed"}` crescendo → crawler/fonte com problema
- `rag_indexed_chunks` caiu bruscamente → reindexação destrutiva acidental

## Qualidade (RAGAS)

`python scripts/evaluate.py` roda o golden dataset (6 perguntas reais) e
reporta faithfulness, answer relevancy e context precision/recall. Rode após
cada mudança de chunking/retrieval/prompt e acompanhe a tendência.

## Tracing (opcional)

`ENABLE_TRACING=true` + extras `opentelemetry-*` instalados → spans do FastAPI
exportados via OTLP (`OTEL_EXPORTER_OTLP_ENDPOINT`) para Jaeger/Tempo/etc.
