"""Aplicação do SAFRA Assistant. Nesta fase: sobe, migra o banco privado com backup e responde à saúde."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from safra_foundation import migrations
from safra_foundation.database import make_engine, ping
from safra_foundation.health import HealthRegistry
from safra_foundation.logging import configure_logging, get_logger
from safra_foundation.web import create_base_app

from .. import __version__
from ..core.config import Settings, load_settings
from ..storage import MIGRATIONS

API_PREFIX = "/api/v1"
log = get_logger("assistant.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(level=settings.log_level, logs_dir=settings.logs_dir if settings.log_to_file else None,
                          console=settings.environment != "test")
        engine = make_engine(settings.database_url)
        health = HealthRegistry()                 # novo a cada inicialização: o app pode subir mais de uma vez
        app.state.engine, app.state.health = engine, health
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
                          docs=settings.environment == "development", lifespan=lifespan)
    app.state.settings = settings

    @app.get(API_PREFIX + "/health", tags=["sistema"], summary="O serviço está no ar?")
    async def health_endpoint(request: Request) -> dict:
        """Rota sem sessão: devolve só o estado geral, o serviço e a versão — nenhum detalhe interno."""
        return {"status": request.app.state.health.report().status, "service": "assistant", "version": __version__}

    return app
