# Roadmap de evolução

## Curto prazo
- **Streaming SSE** no `/chat` (FastAPI `StreamingResponse`) para UX de digitação.
- **Redis** para rate limit + memória conversacional (multi-réplica). As
  interfaces (`RateLimiter`, `ConversationMemory`) já isolam a troca.
- **robots.txt** e backoff exponencial no crawler.
- **Feedback do usuário** (👍/👎 por resposta) persistido para curadoria.

## Médio prazo
- **Adapter LangChain/LlamaIndex** implementando as portas existentes
  (`Retriever`, `LLMProvider`) — ganha o ecossistema sem reescrever o core.
- **Agente ReAct completo** (multi-passo com ferramentas: buscar doc, montar
  payload, validar JSON) evoluindo o modo agente atual.
- **Cache semântico** de respostas (pergunta similar → resposta pronta).
- **Avaliação contínua em CI**: gate de PR com RAGAS mínimo no golden dataset.

## Longo prazo
- **Fine-tuning de embeddings** em pares pergunta↔doc do domínio (PT-BR
  e-commerce) para elevar recall.
- **Multi-tenant** (índices por cliente/parceiro) com namespaces no Qdrant.
- **Sumarização hierárquica** para perguntas amplas ("visão geral da API").
- **Webhooks de atualização**: indexar página alterada em segundos em vez de
  esperar o ciclo de reindexação.

## Princípio
Toda evolução deve passar pelas **portas** existentes. Se uma feature exigir
furar uma porta, o primeiro passo é evoluir o contrato — nunca acoplar a cadeia
a um vendor específico.
