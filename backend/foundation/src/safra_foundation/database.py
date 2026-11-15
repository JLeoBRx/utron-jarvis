"""Motor do banco. SQLite (modo WAL) no SAFRA Core; PostgreSQL no SAFRA Portal em produção (AD-04)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from .errors import StorageError


def sqlite_path(url: str) -> Path | None:
    """Caminho do arquivo quando a URL é de SQLite em disco; ``None`` para memória ou outro banco."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def make_engine(url: str) -> Engine:
    """Cria o motor. Em SQLite liga WAL, chaves estrangeiras e espera por bloqueio em toda conexão."""
    try:
        parsed = make_url(url)
    except SQLAlchemyError as exc:
        raise StorageError("O endereço do banco de dados é inválido.") from exc
    if parsed.get_backend_name() != "sqlite":
        return create_engine(parsed, pool_pre_ping=True)
    path = sqlite_path(url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(parsed, connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection, _record) -> None:  # noqa: ANN001 - assinatura do SQLAlchemy
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            if path is not None:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    return engine


def ping(engine: Engine) -> bool:
    """O banco responde? Usado pela verificação de saúde; nunca lança."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
