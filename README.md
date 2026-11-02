# 🛒 Shopping de Preços — RAG sobre a documentação oficial

Assistente de IA que responde perguntas técnicas sobre a **API do Shopping de Preços**
usando **exclusivamente** a documentação oficial indexada:

- Help Center: <https://documentacao.shoppingdeprecos.com.br/pt>
- API Docs: <https://apidoc.shoppingdeprecos.com.br/>

Ele explica endpoints, autenticação, payloads e erros, gera exemplos em
**Python / JavaScript / PHP** com endpoints reais e cita as fontes (título + URL +
score de confiança) em toda resposta. Se a informação não existir no índice,
responde exatamente: **"Não encontrei essa informação na documentação indexada."**

---

## ✨ Funcionalidades

| Bloco | O que tem |
|---|---|
| **Ingestão (RF01–RF02)** | Crawler assíncrono das duas fontes (sitemap + BFS), ETL com limpeza de HTML/sidebar, extração de endpoints/métodos/exemplos, metadados ricos (`source`, `url`, `section`, `endpoint`, `method`, `updated_at`, `category`) |
| **Chunking (RF03)** | Chunking semântico que **nunca divide blocos de código/payloads**, tamanhos 300/500/800/1000 e overlap 50/100/150 configuráveis, breadcrumb de contexto em cada chunk |
| **Embeddings (RF04)** | OpenAI `text-embedding-3-small/large` ou open source (E5/BGE/Instructor via sentence-transformers) — troca pelo `.env` |
| **Banco vetorial (RF05)** | Camada abstrata: `memory`, **ChromaDB**, **FAISS** (local) e **Qdrant** (produção) sem mudar a lógica de negócio |
| **Retrieval (RF06)** | Similarity top-K, **híbrido (vetorial + BM25 com RRF)**, **MMR** e re-ranking **BGE/Cohere** |
| **Geração (RF07)** | OpenAI (GPT-4.1/5.x), Anthropic (Claude Sonnet), Gemini e modelos locais via **Ollama** (Llama 3, Qwen, DeepSeek) |
| **Grounding (RF08–RF09)** | Resposta só com documentos recuperados; bloco `Fontes:` montado **programaticamente** com título + URL; score de confiança |
| **Código (RF10)** | Geração de exemplos funcionais usando apenas endpoints presentes no contexto |
| **Conversação (RF11)** | Memória das últimas N trocas por sessão + reescrita de follow-ups |
| **Modo agente (RF12)** | O LLM pode planejar buscas adicionais na doc (multi-document retrieval) |
| **API (RNF04)** | FastAPI: `POST /chat`, `POST /ingest`, `POST /reindex`, `GET /health`, `GET /metrics`, `POST /auth/token` |
| **Frontend (RNF05)** | Chat em **Streamlit** com fontes, score e modo agente |
| **Observabilidade (RNF06)** | Logs JSON com `request_id`, métricas Prometheus, dashboards Grafana, OpenTelemetry opcional |
| **Qualidade (RNF07)** | Avaliação **RAGAS** (faithfulness, answer relevancy, context precision/recall) + smoke test do golden dataset |
| **Segurança (RNF09)** | JWT, rate limiting, sanitização de entrada, defesa contra prompt injection |
| **Escala (RNF08)** | Indexação **incremental** por hash de conteúdo, reindexação agendada, versionamento dos HTMLs |

---

## 🚀 Quickstart (local)

> Requisitos: Python **3.12+**

```bash
# 1. Ambiente
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configuração
cp .env.example .env
# edite o .env: provedores, chaves e backend vetorial (veja tabela abaixo)

# 3. Ingestão da documentação (crawl + ETL + indexação)
python scripts/ingest.py --full

# 4. API
uvicorn app.main:app --reload
# Swagger: http://localhost:8000/docs

# 5. Frontend (em outro terminal)
pip install -r requirements-frontend.txt
streamlit run frontend/streamlit_app.py
```

Pergunta rápida sem subir a API:

```bash
python scripts/ask.py "Como autenticar na API?"
python scripts/ask.py --mode agent "Como enviar um produto e depois atualizar o estoque?"
```

### 🧪 Modo demo 100% offline

Sem nenhuma chave de API, o sistema funciona em modo demonstração:

```env
EMBEDDING_PROVIDER=fake
LLM_PROVIDER=fake
VECTOR_BACKEND=memory
RETRIEVAL_MODE=hybrid
```

O `FakeLLM` gera respostas determinísticas e o **BM25 mantém o retrieval lexical
real** — ótimo para testes, CI e para conhecer o fluxo antes de plugar um modelo.

### 🔑 Configuração recomendada para produção

```env
EMBEDDING_PROVIDER=openai          # ou sentence-transformers (E5 multilíngue)
VECTOR_BACKEND=qdrant
RETRIEVAL_MODE=hybrid
USE_RERANKER=true                  # BGE local ou Cohere
LLM_PROVIDER=anthropic             # ou openai / gemini / ollama
REQUIRE_AUTH_CHAT=true
BLOCK_PROMPT_INJECTION=true
REINDEX_INTERVAL_HOURS=24
```

---

## 🐳 Docker

```bash
cp .env.example .env
docker compose up --build                      # API :8000 + frontend :8501
docker compose --profile qdrant up             # + Qdrant :6333
docker compose --profile observability up      # + Prometheus :9090 + Grafana :3000
```

A primeira ingestão dentro do container:

```bash
TOKEN=$(curl -s localhost:8000/auth/token -H 'content-type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -X POST localhost:8000/ingest -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"full": true}'
```

---

## 📡 API

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| `POST` | `/auth/token` | — | Emite JWT (credenciais do `.env`) |
| `POST` | `/chat` | opcional* | Pergunta → resposta com fontes e confiança |
| `POST` | `/ingest` | **JWT** | Ingestão incremental (só páginas alteradas) |
| `POST` | `/reindex` | **JWT** | Reindexação total |
| `GET` | `/health` | — | Status + configuração ativa |
| `GET` | `/metrics` | — | Métricas Prometheus |

\* exigida quando `REQUIRE_AUTH_CHAT=true`.

```bash
curl -X POST localhost:8000/chat -H 'content-type: application/json' -d '{
  "question": "Como atualizar o estoque de um produto?",
  "session_id": "minha-sessao",
  "mode": "chat"
}'
```

Resposta (resumida):

```json
{
  "answer": "Para atualizar o estoque, use o endpoint POST .../atualizaEstoqueProduto ... [1]\n\nFontes:\n[1] Atualiza estoque do produto\nhttps://apidoc.shoppingdeprecos.com.br/atualiza-estoque-produto",
  "sources": [{"index": 1, "title": "Atualiza estoque do produto", "url": "https://...", "score": 0.87}],
  "confidence": 0.87,
  "latency_ms": 1240,
  "used_fallback": false
}
```

---

## 🧱 Estrutura do projeto

```
app/
├── api/            # FastAPI: rotas, schemas, segurança (JWT, rate limit, injection)
├── config/         # Settings (pydantic-settings, .env)
├── ingestion/      # crawler, extractor (HTML→MD), enricher, pipeline incremental
├── rag/            # chunking semântico, prompts, cadeia RAG
├── embeddings/     # OpenAI | sentence-transformers | fake
├── vectorstore/    # memory | Chroma | FAISS | Qdrant (porta única)
├── retrieval/      # vector, BM25, híbrido (RRF), MMR, rerankers
├── generation/     # LLMs (OpenAI/Anthropic/Gemini/Ollama/fake) + memória
├── evaluation/     # golden dataset + RAGAS
├── observability/  # logs JSON, métricas Prometheus, tracing OTel
├── container.py    # composition root (injeção de dependências)
└── main.py         # app FastAPI (middleware, /metrics, reindex agendada)
frontend/           # Streamlit
scripts/            # ingest | reindex | ask | evaluate
tests/              # unitários + integração (100% offline)
docs/               # arquitetura, deploys, monitoramento, evolução
docker/             # Dockerfiles + prometheus.yml
```

---

## 🧠 Decisões de arquitetura

- **Ports & Adapters (Clean Architecture / SOLID / DDD lite).** Cada capacidade
  externa tem uma porta (`VectorStoreBase`, `EmbeddingProvider`, `LLMProvider`,
  `Retriever`, `Reranker`) e adapters concretos. O `container.py` é o único
  lugar que monta o grafo — trocar de tecnologia é mudar o `.env`.
- **SDKs diretos em vez de LangChain no core.** O enunciado lista LangChain como
  preferencial; aqui a orquestração é própria (~200 linhas em `rag/chain.py`)
  com SDKs oficiais por baixo. Motivo: contratos explícitos, zero acoplamento a
  abstrações que mudam rápido e debugging direto. Como as portas são neutras,
  um adapter LangChain/LlamaIndex pode ser plugado depois sem tocar a lógica
  (ver `docs/evolucao.md`).
- **Anti-alucinação em camadas.** (1) system prompt restritivo; (2) fallback
  **verificado programaticamente**; (3) bloco de fontes montado pelo código, não
  pelo LLM; (4) instruções dentro dos documentos são tratadas como dados.
- **Incremental por hash.** O `data/manifest.json` guarda o `content_hash` por
  URL; páginas não alteradas são puladas e páginas alteradas têm os chunks
  antigos removidos antes do upsert — sem lixo no índice.

## ⚠️ Limitações conhecidas (honestas)

- Rate limiting e memória conversacional são **em memória** → para múltiplas
  réplicas, troque por Redis (interfaces prontas para isso).
- O login JWT usa credenciais do `.env` → em produção, plugue um IdP/SSO.
- O crawler respeita um delay configurável, mas **não interpreta robots.txt**.
- RAGAS exige LLM juiz (chave OpenAI) e os pacotes opcionais `ragas`/`datasets`.

---

## ✅ Testes

```bash
pip install -r requirements-dev.txt
pytest -q            # 30 testes, 100% offline (fakes + fixtures HTML reais)
```

Avaliação de qualidade (golden dataset com as perguntas reais do domínio):

```bash
python scripts/evaluate.py --no-ragas   # smoke test sem dependências pesadas
python scripts/evaluate.py              # métricas RAGAS completas
```

## 📚 Documentação

- [`docs/arquitetura.md`](docs/arquitetura.md) — diagramas Mermaid (ETL, RAG, containers)
- [`docs/deploy-local.md`](docs/deploy-local.md) — passo a passo local e Docker
- [`docs/deploy-cloud.md`](docs/deploy-cloud.md) — Cloud Run / ECS + Qdrant gerenciado
- [`docs/monitoramento.md`](docs/monitoramento.md) — métricas, dashboards e alertas
- [`docs/evolucao.md`](docs/evolucao.md) — roadmap técnico
