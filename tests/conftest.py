"""Configuração dos testes.

CRÍTICO: as variáveis de ambiente são fixadas ANTES de qualquer import de `app.*`,
porque get_settings() usa lru_cache. Os testes rodam 100% offline:
  - VECTOR_BACKEND=memory  - EMBEDDING_PROVIDER=fake  - LLM_PROVIDER=fake
"""

import os

os.environ.update(
    VECTOR_BACKEND="memory",
    EMBEDDING_PROVIDER="fake",
    LLM_PROVIDER="fake",
    RETRIEVAL_MODE="hybrid",
    JWT_SECRET="segredo-de-teste",
    AUTH_USERNAME="admin",
    AUTH_PASSWORD="admin",
    REQUIRE_AUTH_CHAT="false",
    RATE_LIMIT_PER_MINUTE="1000",
    DATA_DIR="data-test",
    REINDEX_INTERVAL_HOURS="0",
)

import pytest  # noqa: E402

from app import container  # noqa: E402
from app.ingestion.crawler import RawPage  # noqa: E402
from app.ingestion.pipeline import IngestionPipeline  # noqa: E402

# --------------------------------------------------------------- fixtures HTML
# Página no estilo Apidog (API Docs): sidebar cheia de links + conteúdo do endpoint
APIDOC_HTML = """
<html><head><title>Atualiza estoque do produto - API Shopping de Preços</title></head>
<body>
<nav class="sidebar">
  <ul>
    <li><a href="/lista-integracoes">Lista integrações</a></li>
    <li><a href="/envio-produto-simples">Envio produto simples</a></li>
    <li><a href="/atualiza-estoque-produto">Atualiza estoque</a></li>
    <li><a href="/atualiza-preco-produto">Atualiza preço</a></li>
    <li><a href="/fluxo-pedidos">Fluxo de pedidos</a></li>
    <li><a href="/notas-fiscais">Notas fiscais</a></li>
  </ul>
</nav>
<main>
  <h1>Atualiza estoque do produto</h1>
  <p>POST https://api.shoppingdeprecos.com.br/atualizaEstoqueProduto</p>
  <p>Última modificação:2026-02-18 18:34:30</p>
  <h2>Autenticação</h2>
  <p>Envie o header Authorization com Basic base64(usuario:senha) e o header
  X-Client com o token de desenvolvedor.</p>
  <h2>Exemplo de requisição</h2>
  <pre><code class="language-bash">curl -X POST https://api.shoppingdeprecos.com.br/atualizaEstoqueProduto \\
 -H "Authorization: Basic XXXX" -H "X-Client: TOKEN" \\
 -d '{"codigo": "SKU123", "estoque": 10}'</code></pre>
  <h2>Resposta</h2>
  <pre><code class="language-json">{"status": true, "protocolo": 123456789}</code></pre>
</main>
</body></html>
"""

HELP_HTML = """
<html><head><title>Introdução à API</title></head>
<body>
<main>
  <h1>Introdução à API</h1>
  <p>A API do Shopping de Preços permite integrar sua loja para envio de produtos,
  atualização de preços e estoque e recebimento de pedidos.</p>
  <h2>Credenciais</h2>
  <p>Crie suas credenciais em https://app.shoppingdeprecos.com.br/usuarios e
  solicite o token de desenvolvedor pelo e-mail contato@fabricadecodigos.com.br.</p>
</main>
</body></html>
"""

PEDIDOS_HTML = """
<html><head><title>Fluxo de pedidos - API Shopping de Preços</title></head>
<body><main>
  <h1>Fluxo de pedidos</h1>
  <p>GET https://api.shoppingdeprecos.com.br/listaPedidos</p>
  <p>Consulte os pedidos recebidos das integrações e confirme o processamento.</p>
</main></body></html>
"""


def make_pages() -> list[RawPage]:
    return [
        RawPage(url="https://apidoc.shoppingdeprecos.com.br/atualiza-estoque-produto",
                html=APIDOC_HTML, source="apidoc", fetched_at="2026-06-10T00:00:00+00:00"),
        RawPage(url="https://documentacao.shoppingdeprecos.com.br/pt/article/introducao-a-api",
                html=HELP_HTML, source="helpcenter", fetched_at="2026-06-10T00:00:00+00:00"),
        RawPage(url="https://apidoc.shoppingdeprecos.com.br/fluxo-pedidos",
                html=PEDIDOS_HTML, source="apidoc", fetched_at="2026-06-10T00:00:00+00:00"),
    ]


@pytest.fixture()
def fresh_container(tmp_path, monkeypatch):
    """Container limpo apontando data_dir para tmp (manifest/snapshots isolados)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    container.reset_container()
    yield container
    container.reset_container()


@pytest.fixture()
def seeded_container(fresh_container):
    """Container com as fixtures já ingeridas (sem rede)."""
    pipeline: IngestionPipeline = fresh_container.get_pipeline()
    pipeline.run(full=True, pages=make_pages())
    fresh_container.refresh_after_ingest()
    return fresh_container
