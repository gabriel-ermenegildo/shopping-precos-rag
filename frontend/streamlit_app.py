"""Frontend Streamlit (RNF05): chat sobre a documentação do Shopping de Preços.

Conversa com a API FastAPI (POST /chat). Rodar:
    streamlit run frontend/streamlit_app.py
"""

from __future__ import annotations

import os
import uuid

import requests
import streamlit as st

st.set_page_config(page_title="Shopping de Preços — Assistente da API", page_icon="🛒")

API_URL_DEFAULT = os.getenv("RAG_API_URL", "http://localhost:8000")

# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("⚙️ Configuração")
    api_url = st.text_input("URL da API", API_URL_DEFAULT)
    mode = st.radio("Modo", ["chat", "agent"], horizontal=True,
                    help="agent = pode fazer buscas extras na documentação")
    token = st.text_input("Bearer token (opcional)", type="password",
                          help="Necessário apenas se REQUIRE_AUTH_CHAT=true")
    if st.button("🧹 Nova conversa"):
        st.session_state.pop("messages", None)
        st.session_state.pop("session_id", None)
        st.rerun()
    st.caption("As respostas usam exclusivamente a documentação oficial indexada.")

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🛒 Assistente da API — Shopping de Preços")
st.caption("Pergunte sobre endpoints, autenticação, payloads, erros e integrações.")

# ----------------------------------------------------------- histórico
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        for src in msg.get("sources", []):
            st.caption(f"[{src['index']}] [{src['title']}]({src['url']}) — score {src['score']}")

# ----------------------------------------------------------- entrada
if question := st.chat_input("Ex.: Como atualizar o estoque de um produto?"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Consultando a documentação..."):
            try:
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                resp = requests.post(
                    f"{api_url.rstrip('/')}/chat",
                    json={"question": question,
                          "session_id": st.session_state.session_id,
                          "mode": mode},
                    headers=headers,
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                st.error(f"Erro ao chamar a API: {exc}")
                st.stop()

        st.markdown(data["answer"])
        meta = f"confiança {data['confidence']:.2f} · {data['latency_ms']} ms"
        st.caption(("⚠️ resposta de fallback · " if data["used_fallback"] else "") + meta)

        if data["sources"]:
            with st.expander(f"📚 Fontes ({len(data['sources'])})"):
                for src in data["sources"]:
                    st.markdown(f"**[{src['index']}] [{src['title']}]({src['url']})** "
                                f"— score `{src['score']}`")

    st.session_state.messages.append(
        {"role": "assistant", "content": data["answer"], "sources": data["sources"]}
    )
