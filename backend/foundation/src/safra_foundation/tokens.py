"""Tokens aleatórios (sessão, bilhete, recuperação de acesso). O banco guarda só o resumo, nunca o token."""
from __future__ import annotations

import hashlib
import hmac
import secrets


def new_token(nbytes: int = 32) -> str:
    """Token imprevisível, seguro para URL. 32 bytes = 256 bits."""
    if nbytes < 16:
        raise ValueError("token curto demais: use pelo menos 16 bytes")
    return secrets.token_urlsafe(nbytes)


def token_digest(token: str) -> str:
    """Resumo SHA-256 do token, para gravar e procurar sem guardar o valor original."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
