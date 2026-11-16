"""Backup e restauração verificados de bancos SQLite. Uma cópia nunca sobrescreve outra e só vale depois de
conferida; restaurar guarda antes o banco atual."""
from __future__ import annotations

import re
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import StorageError

_SAFE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    size: int
    created: float


def _label(text: str, fallback: str) -> str:
    return _SAFE.sub("-", text.lower()).strip("-")[:40] or fallback


def verify_sqlite(path: Path) -> bool:
    """O arquivo é um banco SQLite íntegro? (``PRAGMA integrity_check``)"""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False
    return bool(row) and row[0] == "ok"


def backup_sqlite(source: Path, directory: Path, *, reason: str = "manual", prefix: str = "safra") -> BackupInfo:
    """Copia ``source`` com a API de backup do SQLite (consistente mesmo com o banco em uso) e confere a cópia."""
    if not source.is_file():
        raise StorageError("Não há banco de dados para copiar.")
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{_label(prefix, 'safra')}-{time.strftime('%Y%m%d-%H%M%S')}-{_label(reason, 'manual')}"
    target = directory / f"{stem}.sqlite3"
    counter = 1
    while target.exists():                                  # nunca sobrescreve uma cópia anterior
        counter += 1
        target = directory / f"{stem}-{counter}.sqlite3"
    try:
        origin = sqlite3.connect(source)                    # só leitura de fato: a API de backup não escreve na origem
        try:
            copy = sqlite3.connect(target)
            try:
                origin.backup(copy)
                copy.execute("PRAGMA journal_mode=DELETE")   # a cópia fica num único arquivo, sem -wal nem -shm
                copy.commit()
            finally:
                copy.close()
        finally:
            origin.close()
    except sqlite3.DatabaseError as exc:
        target.unlink(missing_ok=True)
        raise StorageError("O backup falhou: o banco de origem não pôde ser lido.") from exc
    if not verify_sqlite(target):
        target.unlink(missing_ok=True)
        raise StorageError("O backup falhou na conferência de integridade e foi descartado.")
    return BackupInfo(path=target, size=target.stat().st_size, created=target.stat().st_mtime)


def restore_sqlite(backup: Path, target: Path, *, safety_dir: Path, prefix: str = "safra") -> BackupInfo | None:
    """Substitui ``target`` pelo ``backup``, com o serviço PARADO. Confere o backup antes, guarda o banco atual
    em ``safety_dir`` e confere o resultado. Devolve a cópia de segurança do banco substituído (se havia um)."""
    if not verify_sqlite(backup):
        raise StorageError("O arquivo de backup não é um banco íntegro; nada foi alterado.")
    safety = None
    if target.is_file() and target.stat().st_size:
        safety = backup_sqlite(target, safety_dir, reason="antes-de-restaurar", prefix=prefix)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".restaurando")
    shutil.copyfile(backup, partial)
    if not verify_sqlite(partial):
        partial.unlink(missing_ok=True)
        raise StorageError("A cópia restaurada não passou na conferência; o banco atual foi mantido.")
    for suffix in ("-wal", "-shm"):                         # restos do banco antigo não podem ser aplicados ao novo
        target.with_name(target.name + suffix).unlink(missing_ok=True)
    partial.replace(target)
    return safety


def list_backups(directory: Path, *, prefix: str = "safra") -> list[BackupInfo]:
    if not directory.is_dir():
        return []
    files = sorted(directory.glob(f"{_label(prefix, 'safra')}-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [BackupInfo(path=p, size=p.stat().st_size, created=p.stat().st_mtime) for p in files]
