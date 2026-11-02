"""Configuração central do sistema (12-factor: tudo via variáveis de ambiente / .env).

Qualquer componente (crawler, chunker, retriever, LLM, segurança) lê suas opções
daqui. Trocar de banco vetorial, embedding ou LLM = mudar o .env, sem tocar código.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CHUNK_SIZE_PRESETS = (300, 500, 800, 1000)
CHUNK_OVERLAP_PRESETS = (50, 100, 150)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ------------------------------------------------------------------ app
    app_name: str = "shopping-precos-rag"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    data_dir: Path = Path("data")

    # ------------------------------------------------------------ ingestão
    helpcenter_base_url: str = "https://documentacao.shoppingdeprecos.com.br/pt"
    apidoc_base_url: str = "https://apidoc.shoppingdeprecos.com.br"
    crawl_max_pages: int = 400
    crawl_concurrency: int = 4
    crawl_delay_seconds: float = 0.3
    request_timeout_seconds: float = 25.0
    user_agent: str = "ShoppingPrecosRAG/1.0 (+bot de indexacao da documentacao)"
    # 0 = desligado; >0 liga reindexação incremental agendada em background
    reindex_interval_hours: float = 0.0

    # ------------------------------------------------------------- chunking
    chunk_size: int = 800        # presets sugeridos: 300 | 500 | 800 | 1000
    chunk_overlap: int = 100     # presets sugeridos: 50 | 100 | 150

    # ----------------------------------------------------------- embeddings
    # "fake" = determinístico, sem rede (testes/demo); BM25 continua funcionando
    embedding_provider: Literal["openai", "sentence-transformers", "fake"] = "fake"
    embedding_model: str = "intfloat/multilingual-e5-small"  # bom p/ PT-BR
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 32

    # -------------------------------------------------------- banco vetorial
    vector_backend: Literal["memory", "chroma", "faiss", "qdrant"] = "memory"
    collection_name: str = "shopping_precos_docs"
    chroma_dir: Path = Path("data/chroma")
    faiss_dir: Path = Path("data/faiss")
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    # -------------------------------------------------------------- retrieval
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid"
    top_k: int = 5
    fetch_k: int = 20            # candidatos antes de MMR/re-rank
    rrf_k: int = 60              # constante do Reciprocal Rank Fusion
    use_mmr: bool = False
    mmr_lambda: float = 0.5
    score_threshold: float = 0.0  # corte de similaridade (modo vector)
    use_reranker: bool = False
    reranker_provider: Literal["bge", "cohere"] = "bge"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    cohere_api_key: str = ""

    # --------------------------------------------------------------- geração
    llm_provider: Literal["fake", "openai", "anthropic", "gemini", "ollama"] = "fake"
    llm_model: str = ""          # vazio => default do provider (ver generation/providers.py)
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 1200
    max_context_tokens: int = 6000
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # ---------------------------------------------------------- conversação
    memory_max_turns: int = 6          # últimas N trocas pergunta/resposta
    enable_condense: bool = True       # reescreve follow-ups como pergunta standalone
    agent_max_extra_queries: int = 2   # buscas adicionais no modo agente

    # ------------------------------------------------------------- segurança
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    auth_username: str = "admin"
    auth_password: str = "admin"
    require_auth_chat: bool = False    # /ingest e /reindex SEMPRE exigem auth
    rate_limit_per_minute: int = 30
    max_question_chars: int = 2000
    block_prompt_injection: bool = False  # True => 400 em padrões suspeitos

    # -------------------------------------------------------- observabilidade
    cors_origins: str = "*"
    enable_tracing: bool = False       # OpenTelemetry (requer extras instalados)
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_smaller_than_chunk(cls, v: int, info):
        size = info.data.get("chunk_size", 800)
        if v >= size:
            raise ValueError("chunk_overlap deve ser menor que chunk_size")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.data_dir / "raw"):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
