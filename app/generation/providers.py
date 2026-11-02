"""Adapters concretos de LLM (RF07) + factory.

Todos os SDKs são importados de forma *lazy*: só paga a dependência de quem usa.
Defaults de modelo por provedor ficam em DEFAULT_MODELS (sobrescritos por LLM_MODEL).

FakeLLM existe para testes e para o "modo demo offline": ele monta uma resposta
determinística citando o primeiro documento do contexto — suficiente para
exercitar a API, o frontend e os testes de integração sem nenhuma chave.
"""

from __future__ import annotations

import logging

from app.config.settings import Settings
from app.generation.base import LLMProvider, Message, split_system

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "openai": "gpt-4.1",
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3.1",
    "fake": "fake-llm",
}


class FakeLLM(LLMProvider):
    """Determinístico e offline. Ecoa um resumo do contexto citando [1]."""

    name = "fake"
    model = "fake-llm"

    def chat(self, messages: list[Message]) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if "[1]" in last_user or "Documento [1]" in last_user:
            # extrai a 1ª linha útil do primeiro documento do contexto
            snippet = ""
            grab = False
            for line in last_user.splitlines():
                if line.strip().startswith("Documento [1]"):
                    grab = True
                    continue
                if grab and line.strip():
                    snippet = line.strip()[:200]
                    break
            return (
                "Com base na documentação indexada: "
                f"{snippet} [1]\n\n(resposta gerada pelo provedor 'fake' — "
                "configure LLM_PROVIDER no .env para usar um modelo real)"
            )
        return "Não encontrei essa informação na documentação indexada."


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        from openai import OpenAI  # lazy

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def chat(self, messages: list[Message]) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # OpenAI aceita 'system' inline
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return resp.choices[0].message.content or ""


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        from anthropic import Anthropic  # lazy

        self._client = Anthropic(api_key=api_key)
        self.model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def chat(self, messages: list[Message]) -> str:
        system, turns = split_system(messages)  # Anthropic recebe system separado
        resp = self._client.messages.create(
            model=self.model,
            system=system or None,
            messages=turns,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        from google import genai  # lazy (pacote: google-genai)
        from google.genai import types

        self._client = genai.Client(api_key=api_key)
        self._types = types
        self.model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def chat(self, messages: list[Message]) -> str:
        system, turns = split_system(messages)
        contents = [
            self._types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[self._types.Part.from_text(text=m["content"])],
            )
            for m in turns
        ]
        resp = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(
                system_instruction=system or None,
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
            ),
        )
        return resp.text or ""


class OllamaProvider(LLMProvider):
    """Modelos locais (Llama 3, Qwen, DeepSeek...) via API do Ollama."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, temperature: float, max_tokens: int):
        import httpx  # já é dependência do projeto

        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=120)
        self.model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def chat(self, messages: list[Message]) -> str:
        resp = self._http.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")


def create_llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    model = settings.llm_model or DEFAULT_MODELS[provider]
    t, mx = settings.llm_temperature, settings.llm_max_output_tokens

    if provider == "openai":
        return OpenAIProvider(settings.openai_api_key, model, t, mx)
    if provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, model, t, mx)
    if provider == "gemini":
        return GeminiProvider(settings.google_api_key, model, t, mx)
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, model, t, mx)
    logger.info("LLM_PROVIDER=fake — respostas determinísticas de demonstração")
    return FakeLLM()
