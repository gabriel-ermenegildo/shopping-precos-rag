# Deploy local

## Opção A — Python direto (desenvolvimento)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # ajuste provedores/chaves
python scripts/ingest.py --full       # crawl + indexação
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

Frontend em outro terminal:

```bash
pip install -r requirements-frontend.txt
streamlit run frontend/streamlit_app.py   # http://localhost:8501
```

## Opção B — Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- API: <http://localhost:8000> · Frontend: <http://localhost:8501>
- O volume `./data` persiste Chroma/FAISS, `manifest.json` e snapshots HTML.

Primeira ingestão (rota protegida por JWT):

```bash
TOKEN=$(curl -s localhost:8000/auth/token -H 'content-type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -X POST localhost:8000/ingest \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"full": true}'
```

## Backends vetoriais locais

| Backend | Quando usar | Config |
|---|---|---|
| `memory` | testes/demo (volátil) | `VECTOR_BACKEND=memory` |
| `chroma` | padrão local persistente | `VECTOR_BACKEND=chroma` + `CHROMA_DIR` |
| `faiss`  | busca densa muito rápida | `VECTOR_BACKEND=faiss` + `pip install faiss-cpu` |
| `qdrant` | paridade com produção | `docker compose --profile qdrant up` + `VECTOR_BACKEND=qdrant` |

## Problemas comuns

- **Respostas só com fallback** → o índice está vazio: rode `python scripts/ingest.py --full`.
- **401 em /ingest** → gere o token em `/auth/token` (credenciais do `.env`).
- **Reranker/E5 não sobe** → instale `sentence-transformers` (bloco opcional do requirements).
- **Porta ocupada** → `uvicorn app.main:app --port 8080`.
