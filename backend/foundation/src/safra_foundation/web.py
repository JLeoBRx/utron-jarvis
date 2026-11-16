"""Base comum das aplicações web do SAFRA: formato único de erro, identificador de correlação, guarda de
``Host`` e cabeçalhos de segurança. Não conhece nenhum domínio nem nenhum dos dois serviços.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import errors
from .logging import correlation_id, get_logger, new_correlation_id

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
# (escopo ASGI, erro, correlação) -> (corpo, tipo de conteúdo), ou None para usar o JSON padrão
ErrorRenderer = Callable[[Scope, errors.SafraError, str], "tuple[bytes, str] | None"]


def error_response(error: errors.SafraError) -> JSONResponse:
    """Resposta JSON no formato único de erro."""
    return JSONResponse(errors.error_payload(error, correlation_id.get()), status_code=error.status)


def error_for_status(status: int) -> errors.SafraError:
    """Erro do SAFRA correspondente a um status HTTP."""
    kind = _BY_STATUS.get(status)
    if kind is not None:
        return kind()
    error = errors.SafraError("O pedido não pôde ser atendido.")
    error.status, error.code = status, "erro_http"
    return error


class FoundationMiddleware:
    """Camada mais externa: correlação, guarda de ``Host``, cabeçalhos de segurança e a última rede de erro."""

    def __init__(self, app: ASGIApp, *, allowed_hosts: Iterable[str],
                 security_headers: Mapping[str, str] | None = None,
                 render_error: ErrorRenderer | None = None) -> None:
        self.app = app
        self.render_error = render_error
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self.security_headers = dict(SECURITY_HEADERS if security_headers is None else security_headers)

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
                for name, value in self.security_headers.items():
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
                await self._respond(scope, send_with_headers, errors.OriginRefused())
                return
            await self.app(scope, receive, send_with_headers)
        except Exception:                                    # nenhuma exceção sai sem registro nem vaza no corpo
            log.exception("erro não tratado", extra={"path": scope.get("path", "")})
            if scope["type"] == "http" and not started:
                await self._respond(scope, send_with_headers, errors.SafraError())
            else:
                raise
        finally:
            correlation_id.reset(token)

    async def _respond(self, scope: Scope, send: Send, error: errors.SafraError) -> None:
        rendered = None
        if self.render_error is not None:
            try:
                rendered = self.render_error(scope, error, correlation_id.get())
            except Exception:                                # a página de erro não pode causar outro erro
                log.exception("a página de erro falhou")
        if rendered is None:
            body = json.dumps(errors.error_payload(error, correlation_id.get()), ensure_ascii=False).encode("utf-8")
            content_type = b"application/json; charset=utf-8"
        else:
            body, content_type = rendered[0], rendered[1].encode("ascii")
        await send({"type": "http.response.start", "status": error.status,
                    "headers": [(b"content-type", content_type),
                                (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})


def create_base_app(*, title: str, version: str, allowed_hosts: Iterable[str], docs: bool = False,
                    lifespan=None, security_headers: Mapping[str, str] | None = None,  # noqa: ANN001
                    docs_prefix: str = "/api", render_error: ErrorRenderer | None = None) -> FastAPI:
    """Aplicação FastAPI com o comportamento comum. ``docs`` liga a documentação interativa (só desenvolvimento)."""
    app = FastAPI(title=title, version=version, lifespan=lifespan,
                  docs_url=f"{docs_prefix}/docs" if docs else None, redoc_url=None,
                  openapi_url=f"{docs_prefix}/openapi.json" if docs else None)

    @app.exception_handler(errors.SafraError)
    async def _safra_error(_request: Request, exc: errors.SafraError) -> JSONResponse:
        if exc.status >= 500:
            log.error("erro previsto de servidor", extra={"code": exc.code})
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
                   "problem": err.get("msg", "")} for err in exc.errors()]
        return error_response(errors.InvalidInput(details={"fields": fields}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(error_for_status(exc.status_code))

    app.add_middleware(FoundationMiddleware, allowed_hosts=tuple(allowed_hosts), security_headers=security_headers,
                       render_error=render_error)
    return app
