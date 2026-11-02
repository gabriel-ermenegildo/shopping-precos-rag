"""Contrato da camada de geração (RF07).

Qualquer LLM (OpenAI, Anthropic, Gemini, Ollama/local, fake) implementa a mesma
porta. A cadeia RAG conversa só com esta interface — trocar de modelo é trocar
uma variável no .env (LLM_PROVIDER / LLM_MODEL).

Formato de mensagens (neutro, estilo chat):
    [{"role": "system" | "user" | "assistant", "content": "..."}]
"""

from __future__ import annotations

from abc import ABC, abstractmethod

Message = dict[str, str]


class LLMProvider(ABC):
    name: str = "llm"
    model: str = ""

    @abstractmethod
    def chat(self, messages: list[Message]) -> str:
        """Recebe o histórico (system + turnos) e devolve o texto da resposta."""


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    """Separa o prompt de sistema dos turnos (alguns SDKs exigem isso)."""
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    rest = [m for m in messages if m["role"] != "system"]
    return "\n\n".join(system_parts), rest
