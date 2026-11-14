"""Migrações versionadas (Alembic), sempre precedidas de backup verificado quando há dados a proteger."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from ..core.errors import StorageError
from ..core.logging import get_logger
from .backup import BackupInfo, backup_sqlite
from .database import sqlite_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
log = get_logger("storage.migrations")


@dataclass(frozen=True)
class MigrationResult:
    before: str | None
    after: str | None
    backup: BackupInfo | None

    @property
    def changed(self) -> bool:
        return self.before != self.after


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS_DIR.as_posix())
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    except SQLAlchemyError as exc:
        raise StorageError("Não foi possível ler a versão do banco de dados.") from exc


def _protect(engine: Engine, backups_dir: Path | None, reason: str) -> BackupInfo | None:
    """Copia o banco antes de mexer nele, se for um arquivo SQLite que já tem conteúdo."""
    path = sqlite_path(str(engine.url.render_as_string(hide_password=False)))
    if path is None or backups_dir is None or not path.is_file() or path.stat().st_size == 0:
        return None
    with engine.connect() as connection:                    # banco recém-criado, sem nenhuma tabela: nada a proteger
        if not inspect(connection).get_table_names():
            return None
    return backup_sqlite(path, backups_dir, reason=reason)


def _run(engine: Engine, target: str, *, down: bool) -> None:
    config = _config()
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if down:
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)
    except SQLAlchemyError as exc:
        raise StorageError("A migração do banco de dados falhou; o banco ficou como estava.") from exc


def upgrade(engine: Engine, *, backups_dir: Path | None = None, target: str = "head") -> MigrationResult:
    """Leva o banco à versão ``target``. Sem migração pendente, não faz nada (nem backup)."""
    before = current_revision(engine)
    wanted = head_revision() if target == "head" else target
    if before == wanted:
        return MigrationResult(before, before, None)
    backup = _protect(engine, backups_dir, f"antes-de-{wanted}")
    _run(engine, target, down=False)
    after = current_revision(engine)
    log.info("migração aplicada", extra={"before": before, "after": after, "backup": str(backup.path) if backup else ""})
    return MigrationResult(before, after, backup)


def downgrade(engine: Engine, target: str, *, backups_dir: Path | None = None) -> MigrationResult:
    """Retorna o banco à versão ``target`` (``"base"`` desfaz tudo). Sempre com backup antes."""
    before = current_revision(engine)
    backup = _protect(engine, backups_dir, f"antes-de-retornar-a-{target}")
    _run(engine, target, down=True)
    after = current_revision(engine)
    log.info("migração desfeita", extra={"before": before, "after": after, "backup": str(backup.path) if backup else ""})
    return MigrationResult(before, after, backup)
