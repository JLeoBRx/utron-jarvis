"""Guarda de senhas com scrypt (biblioteca padrão). A senha nunca é armazenada nem registrada.

Formato gravado: ``scrypt$N$r$p$sal$resumo`` (sal e resumo em base64 sem preenchimento). Os parâmetros vão
junto para que possam ser endurecidos depois sem invalidar as senhas existentes (``needs_rehash``).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .errors import InvalidInput

MIN_LENGTH = 12
MAX_LENGTH = 256                     # limite superior: senha gigante não pode virar negação de serviço


@dataclass(frozen=True)
class ScryptParams:
    n: int = 2 ** 17                 # custo de CPU e memória (128 MiB por cálculo com r=8)
    r: int = 8
    p: int = 1
    salt_bytes: int = 16
    key_bytes: int = 32

    @property
    def maxmem(self) -> int:
        return 128 * self.n * self.r * 2


DEFAULT_PARAMS = ScryptParams()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def check_policy(password: str) -> None:
    """Regra mínima: comprimento. Recusa com erro de validação, sem repetir a senha na mensagem."""
    if not isinstance(password, str) or len(password) < MIN_LENGTH:
        raise InvalidInput(f"A senha precisa ter pelo menos {MIN_LENGTH} caracteres.", details={"field": "password"})
    if len(password) > MAX_LENGTH:
        raise InvalidInput(f"A senha pode ter no máximo {MAX_LENGTH} caracteres.", details={"field": "password"})


def _derive(password: str, salt: bytes, params: ScryptParams) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=params.n, r=params.r, p=params.p,
                          maxmem=params.maxmem, dklen=params.key_bytes)


def hash_password(password: str, params: ScryptParams = DEFAULT_PARAMS) -> str:
    check_policy(password)
    salt = secrets.token_bytes(params.salt_bytes)
    return "$".join(("scrypt", str(params.n), str(params.r), str(params.p), _b64(salt), _b64(_derive(password, salt, params))))


def _parse(encoded: str) -> tuple[ScryptParams, bytes, bytes] | None:
    parts = encoded.split("$") if isinstance(encoded, str) else []
    if len(parts) != 6 or parts[0] != "scrypt":
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, digest = _unb64(parts[4]), _unb64(parts[5])
    except (ValueError, TypeError):
        return None
    if n < 2 or n & (n - 1) or n > 2 ** 20 or not 1 <= r <= 32 or not 1 <= p <= 16 or not salt or not digest:
        return None
    return ScryptParams(n=n, r=r, p=p, salt_bytes=len(salt), key_bytes=len(digest)), salt, digest


def verify_password(password: str, encoded: str) -> bool:
    """Confere em tempo constante. Valor gravado malformado ou senha fora dos limites: falso, sem exceção."""
    parsed = _parse(encoded)
    if parsed is None or not isinstance(password, str) or not 0 < len(password) <= MAX_LENGTH:
        return False
    params, salt, digest = parsed
    try:
        candidate = _derive(password, salt, params)
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, digest)


def needs_rehash(encoded: str, params: ScryptParams = DEFAULT_PARAMS) -> bool:
    parsed = _parse(encoded)
    if parsed is None:
        return True
    stored = parsed[0]
    return (stored.n, stored.r, stored.p, stored.key_bytes) != (params.n, params.r, params.p, params.key_bytes)
