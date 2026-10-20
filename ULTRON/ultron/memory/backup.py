"""BACKUP — cópias do banco único do JARVIS (memórias, Second Brain, lembretes, grafo, rede).

* ``create_backup``: cópia consistente com o JARVIS rodando (API de backup do SQLite), verificada
  e com nome datado em ``<dados>/backups``; guarda as ``keep`` mais recentes (só apaga arquivos
  que ela mesma criou, pelo prefixo);
* ``backup_if_due``: o backup automático diário (configurável) — chamado pelo agendador do núcleo;
* ``restore_backup``: só com o JARVIS FECHADO. Verifica a integridade do arquivo escolhido,
  guarda o banco atual como ``*.antes-da-restauracao-<data>`` (nada é perdido) e só então troca.
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from ..config import paths
from .store import Database, verify_database_file

log = logging.getLogger("ultron.backup")

PREFIX = "jarvis-"
SUFFIX = ".sqlite3"
META_KEY = "last_backup_at"


def backups_dir() -> Path:
    path = paths.data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_backups(directory: Path | None = None) -> list[dict]:
    """Backups do JARVIS, do mais recente ao mais antigo."""
    directory = directory or backups_dir()
    items = []
    for path in directory.glob(f"{PREFIX}*{SUFFIX}"):
        try:
            stat = path.stat()
        except OSError:
            continue
        items.append({"path": str(path), "name": path.name, "size": stat.st_size, "created": stat.st_mtime})
    return sorted(items, key=lambda item: (item["created"], item["name"]), reverse=True)


def create_backup(db: Database, *, reason: str = "manual", keep: int = 10, directory: Path | None = None,
                  clock=time.time) -> Path:
    directory = directory or backups_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    tag = "".join(c for c in reason.lower() if c.isalnum())[:16] or "manual"
    target = directory / f"{PREFIX}{stamp}-{tag}{SUFFIX}"
    counter = 1
    while target.exists():                                   # dois backups no mesmo segundo
        counter += 1
        target = directory / f"{PREFIX}{stamp}-{tag}-{counter}{SUFFIX}"
    db.backup_to(target)
    try:
        db.set_meta(META_KEY, str(clock()))
    except Exception:                                        # o backup em si já está garantido
        log.warning("não foi possível registrar o horário do backup")
    prune(directory, keep=keep)
    log.info("backup do banco criado: %s", target.name)
    return target


def prune(directory: Path, *, keep: int) -> list[str]:
    removed = []
    for item in list_backups(directory)[max(1, int(keep)):]:
        try:
            Path(item["path"]).unlink()
            removed.append(item["name"])
        except OSError:
            continue
    return removed


def backup_if_due(db: Database, *, interval_hours: float = 24.0, keep: int = 10, directory: Path | None = None,
                  clock=time.time) -> Path | None:
    """Backup automático: só se o último tiver mais de ``interval_hours`` horas."""
    try:
        last = float(db.get_meta(META_KEY, "0") or 0)
    except (TypeError, ValueError):
        last = 0.0
    if clock() - last < max(1.0, float(interval_hours)) * 3600:
        return None
    return create_backup(db, reason="auto", keep=keep, directory=directory, clock=clock)


def restore_backup(source: Path | str, *, database: Path | None = None, clock=time.time) -> dict:
    """Restaura um backup (JARVIS fechado). Devolve o que foi feito, inclusive onde ficou o banco anterior."""
    source = Path(source)
    database = Path(database or paths.database_path())
    ok, detail = verify_database_file(source)
    if not ok:
        raise ValueError(f"backup recusado: {detail}")
    if source.resolve() == database.resolve():
        raise ValueError("o backup escolhido é o próprio banco em uso")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    previous = None
    if database.exists():
        previous = database.with_name(f"{database.name}.antes-da-restauracao-{stamp}")
        shutil.copy2(database, previous)
        for extra in ("-wal", "-shm"):                         # diário de escrita do banco anterior
            sidecar = database.with_name(database.name + extra)
            if sidecar.exists():
                shutil.move(str(sidecar), str(previous.with_name(previous.name + extra)))
    partial = database.with_name(database.name + ".restaurando")
    shutil.copy2(source, partial)
    partial.replace(database)
    ok, detail = verify_database_file(database)
    if not ok:                                               # nunca deixa um banco quebrado no lugar
        if previous is not None:
            shutil.copy2(previous, database)
        raise ValueError(f"restauração desfeita: {detail}")
    log.info("banco restaurado de %s (anterior guardado em %s)", source.name, previous)
    return {"restored_from": str(source), "database": str(database), "previous": str(previous) if previous else None,
            "check": detail}
