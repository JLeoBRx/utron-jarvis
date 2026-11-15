"""Migrações versionadas (Alembic). Cada serviço tem o seu conjunto, a sua tabela de versão e o seu banco.

Antes de migrar um banco que já tem dados, faz backup verificado. Um banco marcado como pertencente a outro
serviço é recusado: os serviços do SAFRA nunca compartilham banco.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .backup import BackupInfo, backup_sqlite
from .database import sqlite_path
from .errors import StorageError
from .logging import get_logger

OWNER_TABLE = "safra_service"
log = get_logger("storage.migrations")


@dataclass(frozen=True)
class MigrationSet:
    """O conjunto de migrações de UM serviço."""
    service: str                     # "assistant" ou "portal": gravado no banco como dono
    directory: Path                  # pasta com env.py e versions/

    @property
    def version_table(self) -> str:
        return f"alembic_version_{self.service}"


@dataclass(frozen=True)
class MigrationResult:
    before: str | None
    after: str | None
    backup: BackupInfo | None

    @property
    def changed(self) -> bool:
        return self.before != self.after


def _config(migrations: MigrationSet) -> Config:
    config = Config()
    config.set_main_option("script_location", migrations.directory.as_posix())
    config.attributes["version_table"] = migrations.version_table
    return config


def head_revision(migrations: MigrationSet) -> str | None:
    return ScriptDirectory.from_config(_config(migrations)).get_current_head()


def current_revision(engine: Engine, migrations: MigrationSet) -> str | None:
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"version_table": migrations.version_table})
            return context.get_current_revision()
    except SQLAlchemyError as exc:
        raise StorageError("Não foi possível ler a versão do banco de dados.") from exc


def database_owner(engine: Engine) -> str | None:
    """Serviço que criou este banco, ou ``None`` se o banco ainda não tem dono."""
    try:
        with engine.connect() as connection:
            if OWNER_TABLE not in inspect(connection).get_table_names():
                return None
            return connection.execute(text(f"SELECT service FROM {OWNER_TABLE} LIMIT 1")).scalar()
    except SQLAlchemyError as exc:
        raise StorageError("Não foi possível identificar o dono do banco de dados.") from exc


def ensure_owner(engine: Engine, migrations: MigrationSet) -> None:
    """Recusa um banco que pertence a outro serviço, ou que tem tabelas mas não tem dono identificado."""
    owner = database_owner(engine)
    if owner is not None and owner != migrations.service:
        raise StorageError(f"Este banco de dados pertence ao serviço '{owner}' e não pode ser usado por "
                           f"'{migrations.service}'. Os serviços do SAFRA não compartilham banco.")
    if owner is None:
        with engine.connect() as connection:
            tables = [name for name in inspect(connection).get_table_names() if name != migrations.version_table]
        if tables:
            raise StorageError("Este banco de dados já tem tabelas de outra origem e não pode ser usado pelo SAFRA.")


def _protect(engine: Engine, migrations: MigrationSet, backups_dir: Path | None, reason: str) -> BackupInfo | None:
    """Copia o banco antes de mexer nele, se for um arquivo SQLite que já tem tabelas."""
    path = sqlite_path(str(engine.url.render_as_string(hide_password=False)))
    if path is None or backups_dir is None or not path.is_file() or path.stat().st_size == 0:
        return None
    with engine.connect() as connection:                    # banco recém-criado, sem nenhuma tabela: nada a proteger
        if not inspect(connection).get_table_names():
            return None
    return backup_sqlite(path, backups_dir, reason=reason, prefix=f"safra-{migrations.service}")


def _run(engine: Engine, migrations: MigrationSet, target: str, *, down: bool) -> None:
    config = _config(migrations)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            if down:
                command.downgrade(config, target)
            else:
                command.upgrade(config, target)
    except SQLAlchemyError as exc:
        raise StorageError("A migração do banco de dados falhou; o banco ficou como estava.") from exc


def upgrade(engine: Engine, migrations: MigrationSet, *, backups_dir: Path | None = None,
            target: str = "head") -> MigrationResult:
    """Leva o banco à versão ``target``. Sem migração pendente, não faz nada (nem backup)."""
    ensure_owner(engine, migrations)
    before = current_revision(engine, migrations)
    wanted = head_revision(migrations) if target == "head" else target
    if before == wanted:
        return MigrationResult(before, before, None)
    backup = _protect(engine, migrations, backups_dir, f"antes-de-{wanted}")
    _run(engine, migrations, target, down=False)
    after = current_revision(engine, migrations)
    log.info("migração aplicada", extra={"service": migrations.service, "before": before, "after": after,
                                         "backup": str(backup.path) if backup else ""})
    return MigrationResult(before, after, backup)


def downgrade(engine: Engine, migrations: MigrationSet, target: str, *,
              backups_dir: Path | None = None) -> MigrationResult:
    """Retorna o banco à versão ``target`` (``"base"`` desfaz tudo). Sempre com backup antes."""
    ensure_owner(engine, migrations)
    before = current_revision(engine, migrations)
    backup = _protect(engine, migrations, backups_dir, f"antes-de-retornar-a-{target}")
    _run(engine, migrations, target, down=True)
    after = current_revision(engine, migrations)
    log.info("migração desfeita", extra={"service": migrations.service, "before": before, "after": after,
                                         "backup": str(backup.path) if backup else ""})
    return MigrationResult(before, after, backup)
