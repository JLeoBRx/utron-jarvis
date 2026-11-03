"""Segurança do gateway: hash de segredos (scrypt), tokens, limites de tentativas e CSRF.

* Segredos de configuração (o segredo de inscrição do agente) ficam só como hash scrypt — gerado por
  ``python -m jarvis_gateway hash-secret`` e guardado no gerenciador de segredos do servidor.
* Tokens (agente, dispositivos, pareamento) são aleatórios (``secrets``) e o banco guarda só o SHA-256 deles.
* Limites de tentativas por chave (IP, dispositivo) em janela deslizante; comparações em tempo constante.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
PAIR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # sem 0/O, 1/I: fácil de ditar e de digitar


def hash_secret(secret: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (SCRYPT_N, SCRYPT_R, SCRYPT_P, base64.b64encode(salt).decode(),
                                       base64.b64encode(digest).decode())


def verify_secret(secret: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(secret.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def pairing_code(length: int = 8) -> str:
    return "".join(secrets.choice(PAIR_ALPHABET) for _ in range(length))


def normalize_code(code: str) -> str:
    return "".join(ch for ch in str(code or "").upper() if ch in PAIR_ALPHABET)


class RateLimiter:
    """No máximo ``limit`` eventos por ``window`` segundos para cada chave."""

    def __init__(self, limit: int, window: float, *, clock=time.monotonic):
        self.limit, self.window, self._clock = int(limit), float(window), clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(str(key), deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10000:                  # memória limitada sob abuso
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


def csrf_ok(cookie_value: str | None, header_value: str | None) -> bool:
    """CSRF por "double submit": o cabeçalho X-CSRF-Token precisa repetir o cookie (só o próprio site lê)."""
    return bool(cookie_value) and bool(header_value) and hmac.compare_digest(str(cookie_value), str(header_value))
