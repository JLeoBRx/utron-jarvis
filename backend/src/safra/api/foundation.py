"""Base comum das APIs do SAFRA: formato único de erro, identificador de correlação, guarda de ``Host`` e
cabeçalhos de segurança. Não conhece nenhum domínio — por isso pode ser usada também pelo SAFRA Portal.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..core import errors
from ..core.logging import correlation_id, get_logger, new_correlation_id

CORRELATION_HEADER = "X-SAFRA-Correlacao"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
_BY_STATUS = {401: errors.NotAuthenticated, 403: errors.Forbidden, 404: errors.NotFound,
              405: errors.MethodNotAllowed, 409: errors.Conflict, 429: errors.RateLimited, 503: errors.Unavailable}
log = get_logger("api")


def _error_response(error: errors.SafraError) -> JSONResponse:
    return JSONResponse(errors.error_payload(error, correlation_id.get()), status_code=error.status)


class FoundationMiddleware:
    """Camada mais externa: correlação, guarda de ``Host``, cabeçalhos de segurança e a última rede de erro."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        cid = new_correlation_id()
        token = correlation_id.set(cid)
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers[CORRELATION_HEADER] = cid
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        try:
            host = Headers(scope=scope).get("host", "").lower()
            if host not in self.allowed_hosts:
                # Pedido endereçado a outro nome: página de terceiros ou DNS rebinding. Recusado antes das rotas.
                log.warning("pedido recusado pelo cabeçalho Host", extra={"path": scope.get("path", "")})
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                await self._respond(send_with_headers, errors.OriginRefused())
                return
            await self.app(scope, receive, send_with_headers)
        except Exception:                                    # nenhuma exceção sai sem registro nem vaza no corpo
            log.exception("erro não tratado", extra={"path": scope.get("path", "")})
            if scope["type"] == "http" and not started:
                await self._respond(send_with_headers, errors.SafraError())
            else:
                raise
        finally:
            correlation_id.reset(token)

    @staticmethod
    async def _respond(send: Send, error: errors.SafraError) -> None:
        body = json.dumps(errors.error_payload(error, correlation_id.get()), ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": error.status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})


def create_base_app(*, title: str, version: str, allowed_hosts: Iterable[str], docs: bool = False,
                    lifespan=None) -> FastAPI:  # noqa: ANN001 - gerenciador de contexto do FastAPI
    """Aplicação FastAPI com o comportamento comum. ``docs`` liga a documentação interativa (só desenvolvimento)."""
    app = FastAPI(title=title, version=version, lifespan=lifespan,
                  docs_url="/api/docs" if docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None)

    @app.exception_handler(errors.SafraError)
    async def _safra_error(_request: Request, exc: errors.SafraError) -> JSONResponse:
        if exc.status >= 500:
            log.error("erro previsto de servidor", extra={"code": exc.code})
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
                   "problem": err.get("msg", "")} for err in exc.errors()]
        return _error_response(errors.InvalidInput(details={"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        kind = _BY_STATUS.get(exc.status_code)
        if kind is not None:
            return _error_response(kind())
        error = errors.SafraError("O pedido não pôde ser atendido.")
        error.status = exc.status_code
        error.code = "erro_http"
        return _error_response(error)

    app.add_middleware(FoundationMiddleware, allowed_hosts=tuple(allowed_hosts))
    return app
