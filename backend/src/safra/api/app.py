"""Aplicação do SAFRA Core. Nesta fase: sobe, migra o banco com backup e responde à verificação de saúde."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .. import __version__
from ..core.config import Settings, load_settings
from ..core.logging import configure_logging, get_logger
from ..monitoring.health import HealthRegistry
from ..storage import migrations
from ..storage.database import make_engine, ping
from .foundation import create_base_app

API_PREFIX = "/api/v1"
log = get_logger("api.app")


def create_core_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    health = HealthRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(level=settings.log_level, logs_dir=settings.logs_dir if settings.log_to_file else None,
                          console=settings.environment != "test")
        engine = make_engine(settings.database_url)
        app.state.engine = engine
        if settings.migrate_on_start:
            result = migrations.upgrade(engine, backups_dir=settings.backups_dir)
            if result.changed:
                log.info("banco atualizado na inicialização", extra={"before": result.before, "after": result.after})
        health.register("storage", lambda: ping(engine))
        health.register("schema", lambda: (migrations.current_revision(engine) == migrations.head_revision(),
                                           "o banco não está na versão esperada"
                                           if migrations.current_revision(engine) != migrations.head_revision() else ""))
        log.info("SAFRA Core iniciado", extra={"version": __version__, "environment": settings.environment})
        try:
            yield
        finally:
            engine.dispose()
            log.info("SAFRA Core encerrado")

    app = create_base_app(title="SAFRA Core", version=__version__, allowed_hosts=settings.allowed_hosts,
                          docs=settings.environment == "development", lifespan=lifespan)
    app.state.settings = settings
    app.state.health = health

    @app.get(API_PREFIX + "/health", tags=["sistema"], summary="O serviço está no ar?")
    async def health_endpoint() -> dict:
        """Rota sem sessão: devolve só o estado geral e a versão — nenhum detalhe interno."""
        return {"status": health.report().status, "version": __version__}

    return app
