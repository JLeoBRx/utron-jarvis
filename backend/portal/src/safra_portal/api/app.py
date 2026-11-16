"""Montagem do SAFRA Portal: banco próprio, autenticação, CMS, painel e site público."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from safra_foundation import errors, migrations
from safra_foundation.database import make_engine, ping
from safra_foundation.health import HealthRegistry
from safra_foundation.logging import configure_logging, get_logger
from safra_foundation.web import create_base_app, error_for_status, error_response

from .. import __version__
from ..auth.service import AuthService
from ..config import Settings, load_settings
from ..infrastructure import MIGRATIONS
from ..infrastructure.db import make_session_factory, transaction
from ..infrastructure.seed import seed_initial_content
from ..media.service import MediaService
from ..public_site import routes as public_routes
from ..public_site.render import STATIC, make_environment, render
from . import admin

log = get_logger("portal.app")
API_PREFIX = "/admin/api"
CONTENT_SECURITY_POLICY = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                           "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; "
                           "frame-ancestors 'none'; manifest-src 'self'")
ERROR_TITLES = {403: "Acesso não permitido", 404: "Página não encontrada", 405: "Método não permitido",
                429: "Muitas tentativas", 500: "Algo deu errado", 503: "Serviço indisponível"}


class CachedStaticFiles(StaticFiles):
    """Arquivos estáticos com política de cache explícita (o padrão do Portal é não guardar nada)."""

    def __init__(self, *args, cache_control: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        path = str(args[0]) if args else ""
        response.headers["Cache-Control"] = "no-cache" if path.endswith(".html") else self.cache_control
        return response


def find_admin_dist(settings: Settings) -> Path | None:
    candidates = [settings.admin_dist] if settings.admin_dist else [
        Path(__file__).resolve().parents[1] / "admin_dist",                    # copiado para dentro do pacote na imagem
        Path(__file__).resolve().parents[5] / "apps" / "admin" / "dist",       # repositório, em desenvolvimento
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    templates = make_environment()

    def error_page(error: errors.SafraError, correlation: str) -> str:
        return render(templates, "error.html", status=error.status, title=ERROR_TITLES.get(error.status, "Erro"),
                      message=error.message, correlation=correlation,
                      seo={"title": f"{ERROR_TITLES.get(error.status, 'Erro')} — SAFRA", "description": "",
                           "canonical": "", "type": "website", "image": "", "noindex": True},
                      site={"tagline": "", "footer_text": "", "footer_links": []}, nav=[], footer_nav=[],
                      current_path="", version=__version__)

    def render_error(scope: Scope, error: errors.SafraError, correlation: str):
        if scope.get("type") != "http" or str(scope.get("path", "")).startswith(API_PREFIX):
            return None                                           # a API responde sempre em JSON
        return error_page(error, correlation).encode("utf-8"), "text/html; charset=utf-8"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(level=settings.log_level, logs_dir=settings.logs_dir if settings.log_to_file else None,
                          console=settings.environment != "test")
        engine = make_engine(settings.database_url)
        if settings.migrate_on_start:
            result = migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
            if result.changed:
                log.info("banco atualizado na inicialização", extra={"before": result.before, "after": result.after})
        else:
            migrations.ensure_owner(engine, MIGRATIONS)
        factory = make_session_factory(engine)
        health = HealthRegistry()                 # novo a cada inicialização: o app pode subir mais de uma vez
        app.state.engine, app.state.session_factory, app.state.health = engine, factory, health
        app.state.auth = AuthService(settings)
        app.state.media = MediaService(settings.media_dir, settings.max_upload_bytes)
        with transaction(factory) as db:
            app.state.auth.purge_expired(db)
            if settings.seed_on_start and seed_initial_content(db):
                log.info("conteúdo inicial criado")
        health.register("storage", lambda: ping(engine))
        health.register("schema", lambda: migrations.current_revision(engine, MIGRATIONS)
                        == migrations.head_revision(MIGRATIONS))
        log.info("SAFRA Portal iniciado", extra={"version": __version__, "environment": settings.environment})
        try:
            yield
        finally:
            engine.dispose()
            log.info("SAFRA Portal encerrado")

    headers = {"Content-Security-Policy": CONTENT_SECURITY_POLICY, "X-Content-Type-Options": "nosniff",
               "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
               "Permissions-Policy": "camera=(), microphone=(), geolocation=()", "Cache-Control": "no-store"}
    if settings.secure_cookies:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    app = create_base_app(title="SAFRA Portal", version=__version__, allowed_hosts=settings.allowed_hosts,
                          docs=settings.environment == "development", docs_prefix=API_PREFIX, lifespan=lifespan,
                          security_headers=headers, render_error=render_error)
    app.state.settings, app.state.templates = settings, templates

    def respond(request: Request, error: errors.SafraError) -> Response:
        if request.url.path.startswith(API_PREFIX):
            return error_response(error)
        from safra_foundation.logging import correlation_id
        return HTMLResponse(error_page(error, correlation_id.get()), status_code=error.status,
                            headers={"Cache-Control": "no-store"})

    @app.exception_handler(errors.SafraError)
    async def _safra_error(request: Request, exc: errors.SafraError) -> Response:
        if exc.status >= 500:
            log.error("erro previsto de servidor", extra={"code": exc.code})
        return respond(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        return respond(request, error_for_status(exc.status_code))

    app.include_router(admin.router)
    app.include_router(public_routes.preview_router)

    admin_dist = find_admin_dist(settings)

    @app.get("/admin", include_in_schema=False)
    async def _admin_redirect() -> RedirectResponse:
        return RedirectResponse("/admin/", status_code=308)

    if admin_dist is not None:
        app.mount("/admin", CachedStaticFiles(directory=str(admin_dist), html=True,
                                              cache_control="public, max-age=31536000, immutable"), name="admin")
    else:
        @app.get("/admin/", include_in_schema=False)
        async def _admin_missing() -> HTMLResponse:
            return HTMLResponse(render(templates, "admin_missing.html"), status_code=503,
                                headers={"Cache-Control": "no-store"})

    app.mount("/static", CachedStaticFiles(directory=str(STATIC), cache_control="public, max-age=3600"), name="static")
    app.include_router(public_routes.router)
    return app
