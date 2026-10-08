"""Importação única dos dados do JARVIS legado.

Lê ``%LOCALAPPDATA%\\JARVIS\\assistant.sqlite3`` em modo somente leitura e copia fatos,
preferências permitidas e automações para a base do ULTRON. Executa uma única vez
(registrado na tabela ``meta``). O banco legado nunca é alterado.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .preference_memory import ALLOWED
from .store import Database, looks_secret

log = logging.getLogger("ultron.legacy")

_PREF_MAP = {"profile_name": "profile_name", "address_me_as": "address_me_as", "city": "city",
             "language": "language"}


def import_jarvis(db: Database, legacy_path: Path | None) -> dict[str, int]:
    report = {"facts": 0, "preferences": 0, "automations": 0, "skipped": 0}
    if legacy_path is None or not Path(legacy_path).is_file():
        return report
    if db.get_meta("legacy_jarvis_imported"):
        return report
    uri = Path(legacy_path).resolve().as_uri() + "?mode=ro"
    try:
        legacy = sqlite3.connect(uri, uri=True, timeout=3)
    except sqlite3.Error as exc:
        log.warning("banco do JARVIS não pôde ser aberto: %s", exc)
        return report
    try:
        tables = {r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "memories" in tables:
            for subject, fact in legacy.execute("SELECT subject, fact FROM memories"):
                if looks_secret(subject) or looks_secret(fact):
                    report["skipped"] += 1
                    continue
                db.execute("INSERT OR IGNORE INTO facts(subject,fact,source,confidence,created_at,updated_at) "
                           "VALUES(?,?,'jarvis',1.0,strftime('%s','now'),strftime('%s','now'))",
                           (str(subject)[:80], str(fact)[:600]))
                report["facts"] += 1
        if "preferences" in tables:
            for name, value in legacy.execute("SELECT name, value FROM preferences"):
                target = _PREF_MAP.get(name)
                if target in ALLOWED and not looks_secret(value):
                    db.execute("INSERT OR IGNORE INTO preferences(name,value,updated_at) "
                               "VALUES(?,?,strftime('%s','now'))", (target, str(value)[:200]))
                    report["preferences"] += 1
        if "automations" in tables:
            for name, trigger, tool, args, enabled in legacy.execute(
                    "SELECT name, trigger_text, tool_name, arguments, enabled FROM automations"):
                db.execute("INSERT OR IGNORE INTO automations(name,trigger_text,tool_name,arguments,enabled) "
                           "VALUES(?,?,?,?,?)", (name, trigger, tool, args, enabled))
                report["automations"] += 1
    finally:
        legacy.close()
    db.set_meta("legacy_jarvis_imported", str(report))
    log.info("dados do JARVIS importados: %s", report)
    return report
