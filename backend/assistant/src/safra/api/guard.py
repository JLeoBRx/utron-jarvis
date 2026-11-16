"""Guarda dos pedidos que alteram dados na API local (decisão AD-25).

O Assistant escuta só em 127.0.0.1 e o cabeçalho ``Host`` já é conferido (defesa contra DNS rebinding). Falta
impedir que uma página aberta no navegador — de qualquer site — mande o navegador gravar algo no Assistant:

* ``Origin`` presente e diferente da própria interface → recusado;
* ``Sec-Fetch-Site: cross-site`` → recusado;
* corpo que não seja JSON → recusado (formulários de outros sites não conseguem enviar JSON sem pré-verificação CORS,
  e a API não responde a CORS).

Pedidos sem ``Origin`` vêm de programas deste computador (não de páginas): esses já teriam acesso aos mesmos
arquivos. Sessões locais (bilhete da casca, código do navegador) chegam na Fase 4.
"""
from __future__ import annotations

import json

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from safra_foundation import errors
from safra_foundation.logging import correlation_id, get_logger

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
log = get_logger("assistant.guard")


class UnsupportedMedia(errors.SafraError):
    code = "tipo_nao_aceito"
    status = 415
    default_message = "Envie os dados em JSON."


class LocalOriginGuard:
    def __init__(self, app: ASGIApp, *, allowed_origins: tuple[str, ...]) -> None:
        self.app = app
        self.allowed = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in UNSAFE:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        problem: errors.SafraError | None = None
        if origin is not None and origin not in self.allowed:
            problem = errors.OriginRefused()
        elif headers.get("sec-fetch-site") == "cross-site":
            problem = errors.OriginRefused()
        else:
            has_body = headers.get("transfer-encoding") or int(headers.get("content-length") or 0) > 0
            if has_body and not headers.get("content-type", "").split(";")[0].strip().lower() == "application/json":
                problem = UnsupportedMedia()
        if problem is None:
            await self.app(scope, receive, send)
            return
        log.warning("pedido recusado pela guarda local", extra={"path": scope.get("path", ""), "code": problem.code})
        body = json.dumps(errors.error_payload(problem, correlation_id.get()), ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": problem.status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})
