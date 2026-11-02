"""Memória conversacional por sessão (RF11).

Guarda as últimas N trocas (pergunta/resposta) por session_id, em memória.
É suficiente para uma única réplica da API. Para múltiplas réplicas em
produção, troque o dicionário por Redis mantendo esta mesma interface
(get / add) — nenhum outro módulo precisa mudar.
"""

from __future__ import annotations

import threading
from collections import deque

from app.generation.base import Message


class ConversationMemory:
    def __init__(self, max_turns: int = 6):
        # cada "turno" = 2 mensagens (user + assistant)
        self._max_messages = max(1, max_turns) * 2
        self._sessions: dict[str, deque[Message]] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str) -> list[Message]:
        with self._lock:
            return list(self._sessions.get(session_id, ()))

    def add(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            dq = self._sessions.setdefault(session_id, deque(maxlen=self._max_messages))
            dq.append({"role": "user", "content": question})
            dq.append({"role": "assistant", "content": answer})

    def clear(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._sessions.clear()
            else:
                self._sessions.pop(session_id, None)
