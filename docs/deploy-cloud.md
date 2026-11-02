# Deploy em nuvem

A API é um container ASGI stateless (estado fica no banco vetorial + `data/`),
então qualquer plataforma de containers serve. Receitas resumidas:

## Google Cloud Run + Qdrant Cloud

```bash
# build e push
gcloud builds submit --tag gcr.io/SEU_PROJETO/sp-rag -f docker/Dockerfile .

# deploy
gcloud run deploy sp-rag \
  --image gcr.io/SEU_PROJETO/sp-rag --region southamerica-east1 \
  --allow-unauthenticated --memory 1Gi --cpu 1 \
  --set-env-vars VECTOR_BACKEND=qdrant,QDRANT_URL=https://xxx.cloud.qdrant.io,EMBEDDING_PROVIDER=openai,LLM_PROVIDER=anthropic,REQUIRE_AUTH_CHAT=true \
  --set-secrets OPENAI_API_KEY=openai-key:latest,ANTHROPIC_API_KEY=anthropic-key:latest,QDRANT_API_KEY=qdrant-key:latest,JWT_SECRET=jwt-secret:latest
```

- **Segredos** sempre via Secret Manager (nunca no `.env` versionado).
- **Ingestão agendada**: Cloud Scheduler → `POST /ingest` com header
  `Authorization: Bearer <token>` (ou `REINDEX_INTERVAL_HOURS=24` se a réplica
  for única e estável).
- Mín. de instâncias = 1 evita cold start no primeiro `/chat` do dia.

## AWS ECS Fargate (equivalente)

1. Push da imagem para o ECR.
2. Task definition com as mesmas variáveis (segredos no Secrets Manager).
3. Service atrás de um ALB (health check em `/health`).
4. EventBridge Scheduler chama `/ingest` diariamente.

## Checklist de produção

- [ ] `REQUIRE_AUTH_CHAT=true`, `BLOCK_PROMPT_INJECTION=true`
- [ ] `JWT_SECRET` forte e rotacionável; credenciais demo trocadas por IdP/SSO
- [ ] `VECTOR_BACKEND=qdrant` gerenciado (snapshots/backup habilitados)
- [ ] `USE_RERANKER=true` (Cohere em serverless; BGE se houver CPU/GPU dedicada)
- [ ] Rate limit/memória conversacional migrados para Redis se houver >1 réplica
- [ ] `CORS_ORIGINS` restrito ao domínio do frontend
- [ ] Prometheus raspando `/metrics` + alertas (ver monitoramento.md)
