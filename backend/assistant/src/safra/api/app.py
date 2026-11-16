"""Aplicação do SAFRA Assistant: banco privado com backup, API local para a interface e o console, e a interface
compilada servida no mesmo endereço (127.0.0.1). Sem CORS: só a própria interface usa a API."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from starlette.middleware import Middleware
from starlette.staticfiles import StaticFiles

from safra_foundation import migrations
from safra_foundation.database import make_engine, ping
from safra_foundation.health import HealthRegistry
from safra_foundation.logging import configure_logging, get_logger
from safra_foundation.web import create_base_app

from .. import __version__
from ..core.config import Settings, load_settings
from ..monitoring.resources import ResourceSampler
from ..storage import MIGRATIONS
from ..storage.db import make_session_factory
from . import routes
from .guard import LocalOriginGuard

API_PREFIX = "/api/v1"
log = get_logger("assistant.api")
CONTENT_SECURITY_POLICY = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
                           "connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'; manifest-src 'self'")
SECURITY_HEADERS = {"Content-Security-Policy": CONTENT_SECURITY_POLICY, "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
                    "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()"}
UI_MISSING = """<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>SAFRA Assistant</title></head>
<body><h1>A interface do SAFRA não foi compilada</h1><p>A API está no ar. Para ver a interface, compile-a:
<code>npm ci</code> e <code>npm run build -w @safra/assistant-ui</code> na raiz do repositório.</p></body></html>"""


class _CachedStatic(StaticFiles):
    """Arquivos da interface: os com nome versionado ficam em cache; o index.html é sempre conferido."""

    def file_response(self, *args, **kwargs) -> Response:  # noqa: ANN002, ANN003
        response = super().file_response(*args, **kwargs)
        path = str(args[0]) if args else ""
        response.headers["Cache-Control"] = "no-cache" if path.endswith(".html") else "public, max-age=31536000, immutable"
        return response


def find_ui_dist(settings: Settings) -> Path | None:
    candidates = [settings.ui_dist] if settings.ui_dist else [
        Path(__file__).resolve().parents[1] / "ui_dist",                        # copiada para dentro do pacote no instalador
        Path(__file__).resolve().parents[5] / "apps" / "assistant" / "dist",    # repositório, em desenvolvimento
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(level=settings.log_level, logs_dir=settings.logs_dir if settings.log_to_file else None,
                          console=settings.environment != "test")
        engine = make_engine(settings.database_url)
        health = HealthRegistry()                 # novo a cada inicialização: o app pode subir mais de uma vez
        app.state.engine, app.state.health = engine, health
        app.state.session_factory = make_session_factory(engine)
        app.state.resources = ResourceSampler()
        app.state.started_at = time.time()
        if settings.migrate_on_start:
            result = migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
            if result.changed:
                log.info("banco atualizado na inicialização", extra={"before": result.before, "after": result.after})
        else:
            migrations.ensure_owner(engine, MIGRATIONS)
        health.register("storage", lambda: ping(engine))
        health.register("schema", lambda: migrations.current_revision(engine, MIGRATIONS)
                        == migrations.head_revision(MIGRATIONS))
        log.info("SAFRA Assistant iniciado", extra={"version": __version__, "environment": settings.environment})
        try:
            yield
        finally:
            engine.dispose()
            log.info("SAFRA Assistant encerrado")

    app = create_base_app(title="SAFRA Assistant", version=__version__, allowed_hosts=settings.allowed_hosts,
                          docs=settings.environment == "development", lifespan=lifespan, security_headers=SECURITY_HEADERS)
    # dentro da camada de base (correlação e cabeçalhos valem também para as recusas da guarda)
    app.user_middleware.append(Middleware(LocalOriginGuard, allowed_origins=settings.allowed_origins))
    app.state.settings = settings

    @app.get(API_PREFIX + "/health", tags=["sistema"], summary="O serviço está no ar?")
    async def health_endpoint(request: Request) -> dict:
        """Rota sem sessão: devolve só o estado geral, o serviço e a versão — nenhum detalhe interno."""
        return {"status": request.app.state.health.report().status, "service": "assistant", "version": __version__}

    app.include_router(routes.router)
    ui_dist = find_ui_dist(settings)
    if ui_dist is not None:
        app.mount("/", _CachedStatic(directory=str(ui_dist), html=True), name="interface")
    else:
        @app.get("/", include_in_schema=False)
        async def _ui_missing() -> HTMLResponse:
            return HTMLResponse(UI_MISSING, status_code=503)
    return app
