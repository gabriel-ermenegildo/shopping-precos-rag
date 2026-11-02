"""Segurança da API (RNF09): JWT, rate limiting, sanitização e anti prompt-injection.

Decisões (documentadas também no README):
- JWT HS256 com PyJWT; login demo via AUTH_USERNAME/AUTH_PASSWORD do .env
  (em produção: troque por IdP/SSO; a verificação fica isolada aqui).
- Rate limit: sliding window em memória, por IP. Para múltiplas réplicas,
  troque por Redis mantendo a interface allow().
- Prompt injection: defesa em camadas — (1) o system prompt manda ignorar
  instruções vindas dos documentos; (2) heurística opcional bloqueia padrões
  óbvios na ENTRADA do usuário (block_prompt_injection=True => HTTP 400).
"""

from __future__ import annotations

import hmac
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------- JWT
def create_access_token(username: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")


def check_credentials(username: str, password: str, settings: Settings) -> bool:
    ok_user = hmac.compare_digest(username.encode(), settings.auth_username.encode())
    ok_pass = hmac.compare_digest(password.encode(), settings.auth_password.encode())
    return ok_user and ok_pass


def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Dependency: exige Bearer token válido (usada em /ingest e /reindex)."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente")
    return verify_token(creds.credentials, settings)


def optional_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict | None:
    """Dependency: exige token só se REQUIRE_AUTH_CHAT=true (usada em /chat)."""
    if not settings.require_auth_chat:
        return None
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente")
    return verify_token(creds.credentials, settings)


# ------------------------------------------------------------ rate limit
class RateLimiter:
    """Sliding window por chave (IP). Thread-safe, em memória."""

    def __init__(self, max_per_minute: int):
        self.max = max_per_minute
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= self.max:
                return False
            dq.append(now)
            return True


_rate_limiter: RateLimiter | None = None


def rate_limit(request: Request, settings: Settings = Depends(get_settings)) -> None:
    global _rate_limiter
    if settings.rate_limit_per_minute <= 0:
        return
    if _rate_limiter is None or _rate_limiter.max != settings.rate_limit_per_minute:
        _rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    key = request.client.host if request.client else "anon"
    if not _rate_limiter.allow(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Limite de requisições excedido. Tente novamente em instantes.")


# ------------------------------------------- sanitização / prompt injection
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"ignore\s+(todas?\s+as\s+)?(instru[cç][oõ]es|regras)( anteriores| acima)?",
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"(revele|mostre|imprima|print)\s+(o\s+)?(seu\s+)?(system\s*prompt|prompt\s+de\s+sistema)",
        r"voc[eê]\s+agora\s+[eé]\b",
        r"\bDAN\b.{0,30}\bmode\b",
        r"finja\s+que\s+(voc[eê]|n[aã]o)\b",
        r"disregard\s+(the\s+)?(rules|context)",
    )
]


def sanitize_question(text: str, max_chars: int) -> str:
    text = _CONTROL_CHARS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pergunta vazia")
    if len(text) > max_chars:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Pergunta excede o limite de {max_chars} caracteres",
        )
    return text


def detect_prompt_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)
