# Arquitetura

## Visão geral (containers)

```mermaid
flowchart LR
    subgraph Fontes["Documentação oficial"]
        HC[Help Center<br/>documentacao.shoppingdeprecos.com.br]
        AD[API Docs<br/>apidoc.shoppingdeprecos.com.br]
    end

    subgraph App["RAG API (FastAPI)"]
        ING[Pipeline de ingestão]
        CHAIN[Cadeia RAG]
        SEC[Segurança<br/>JWT · rate limit · sanitização]
    end

    VS[(Banco vetorial<br/>Chroma · FAISS · Qdrant)]
    LLM[LLM<br/>OpenAI · Anthropic · Gemini · Ollama]
    FE[Frontend Streamlit]
    PROM[Prometheus]
    GRAF[Grafana]

    HC --> ING
    AD --> ING
    ING --> VS
    FE -->|POST /chat| SEC --> CHAIN
    CHAIN <--> VS
    CHAIN <--> LLM
    App -->|GET /metrics| PROM --> GRAF
```

## Pipeline ETL (RF01–RF03)

```mermaid
flowchart TD
    A[Crawler assíncrono<br/>sitemap + BFS por fonte] --> B[Extractor<br/>HTML → Markdown<br/>poda de sidebar/ruído<br/>código vira bloco fenced]
    B --> C[Enricher<br/>source · url · section · endpoint<br/>method · updated_at · category · hash]
    C --> D{Hash mudou?<br/>manifest.json}
    D -- não --> SKIP[Pula página<br/>indexação incremental]
    D -- sim --> E[Remove chunks antigos da URL]
    E --> F[Chunking semântico<br/>código/payload nunca dividido<br/>breadcrumb de contexto]
    F --> G[Embeddings em lotes]
    G --> H[(Upsert no banco vetorial)]
    H --> I[Snapshot do HTML em data/raw<br/>versionamento]
```

## Fluxo de uma pergunta (POST /chat)

```mermaid
sequenceDiagram
    participant U as Usuário
    participant API as FastAPI
    participant SEC as Segurança
    participant CH as RAGChain
    participant R as Retriever híbrido
    participant RR as Reranker (opcional)
    participant L as LLM

    U->>API: POST /chat {question, session_id, mode}
    API->>SEC: rate limit + auth opcional + sanitização
    SEC-->>API: ok (ou 400/401/429)
    API->>CH: answer()
    CH->>L: condensa follow-up (se houver histórico)
    CH->>R: retrieve(pergunta, fetch_k)
    Note over CH,R: modo agente: LLM pode pedir<br/>buscas extras (multi-document)
    R-->>CH: candidatos (vetorial + BM25 fundidos via RRF)
    CH->>RR: re-rank top_k (BGE/Cohere)
    CH->>CH: compressão de contexto<br/>(dedupe + orçamento de tokens)
    alt nenhum documento
        CH-->>API: "Não encontrei essa informação..." (fallback)
    else documentos encontrados
        CH->>L: system + histórico + CONTEXTO + pergunta
        L-->>CH: resposta com citações [n]
        CH->>CH: anexa bloco Fontes (título + URL)<br/>programaticamente
        CH-->>API: answer + sources + confidence
    end
    API-->>U: JSON
```

## Portas e adapters (Clean Architecture)

```mermaid
classDiagram
    class Retriever { <<port>> retrieve(query, k) }
    class VectorStoreBase { <<port>> upsert() search() delete_by_url() }
    class EmbeddingProvider { <<port>> embed_documents() embed_query() }
    class LLMProvider { <<port>> chat(messages) }

    Retriever <|-- VectorRetriever
    Retriever <|-- BM25Retriever
    Retriever <|-- HybridRetriever
    VectorStoreBase <|-- InMemoryVectorStore
    VectorStoreBase <|-- ChromaStore
    VectorStoreBase <|-- FaissStore
    VectorStoreBase <|-- QdrantStore
    EmbeddingProvider <|-- OpenAIEmbeddings
    EmbeddingProvider <|-- SentenceTransformersEmbeddings
    EmbeddingProvider <|-- FakeEmbeddings
    LLMProvider <|-- OpenAIProvider
    LLMProvider <|-- AnthropicProvider
    LLMProvider <|-- GeminiProvider
    LLMProvider <|-- OllamaProvider
    LLMProvider <|-- FakeLLM

    HybridRetriever --> VectorRetriever
    HybridRetriever --> BM25Retriever
    VectorRetriever --> VectorStoreBase
    VectorRetriever --> EmbeddingProvider
```

O `app/container.py` (composition root) é o único módulo que instancia adapters
concretos. Rotas e cadeia conhecem apenas as portas — por isso trocar Chroma por
Qdrant, ou GPT por Claude, é alterar **uma linha do `.env`**.

## Anti-alucinação (defesa em profundidade)

1. **Prompt**: o system prompt proíbe conhecimento externo e exige a frase de
   fallback exata quando o contexto não cobre a pergunta.
2. **Código**: se o retrieval volta vazio, a cadeia devolve o fallback **sem
   chamar o LLM**; se o LLM emitir o fallback, as fontes são zeradas.
3. **Fontes**: o bloco `Fontes:` (título + URL) é montado pelo código a partir
   dos chunks realmente usados — o LLM não tem como inventar URLs.
4. **Injection**: documentos são declarados "dados, não comandos" no prompt, e
   a entrada do usuário passa por sanitização + heurística opcional de bloqueio.
