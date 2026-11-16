"""Importação única dos dados do JARVIS legado.

Lê ``%LOCALAPPDATA%\\JARVIS\\assistant.sqlite3`` em modo somente leitura e copia fatos,
preferências permitidas e automações para a base do JARVIS. Executa uma única vez
(registrado na tabela ``meta``). O banco legado nunca é alterado.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .preference_memory import ALLOWED
from .store import Database, looks_secret

log = logging.getLogger("ultron.legacy")

_PREF_MAP = {"profile_name": "profile_name", "address_me_as": "address_me_as", "city": "city",
             "language": "language"}

# Ferramentas das automações do JARVIS original → skills atuais (os argumentos são os mesmos).
LEGACY_TOOLS = {"open_app": "app.open", "search_web": "web.search", "open_url": "web.open_url",
                "control_volume": "audio.volume", "control_media": "audio.media", "search_files": "fs.search",
                "take_screenshot": "vision.screenshot"}
LEGACY_META = "legacy_automations"          # nomes das automações vindas do original (JSON)


def legacy_automation_names(db: Database) -> set[str]:
    try:
        return {str(n).lower() for n in json.loads(db.get_meta(LEGACY_META) or "[]")}
    except ValueError:
        return set()


def _remember_legacy(db: Database, names) -> None:
    known = legacy_automation_names(db) | {str(n).lower() for n in names}
    db.set_meta(LEGACY_META, json.dumps(sorted(known)))


def repair_automations(db: Database) -> int:
    """Converte automações gravadas com o nome antigo da ferramenta (importações anteriores a esta
    correção) para o nome da skill atual. Idempotente; devolve quantas foram convertidas."""
    rows = db.query("SELECT name, tool_name FROM automations")
    fixed = [(LEGACY_TOOLS[r["tool_name"]], r["name"]) for r in rows if r["tool_name"] in LEGACY_TOOLS]
    for skill, name in fixed:
        db.execute("UPDATE automations SET tool_name=? WHERE name=?", (skill, name))
    if fixed:
        _remember_legacy(db, [name for _, name in fixed])
        log.info("automações do JARVIS original convertidas para as skills atuais: %d", len(fixed))
    return len(fixed)


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
                cursor = db.execute("INSERT OR IGNORE INTO facts(subject,fact,source,confidence,created_at,updated_at) "
                                    "VALUES(?,?,'jarvis',1.0,strftime('%s','now'),strftime('%s','now'))",
                                    (str(subject)[:80], str(fact)[:600]))
                report["facts"] += cursor.rowcount or 0
        if "preferences" in tables:
            for name, value in legacy.execute("SELECT name, value FROM preferences"):
                target = _PREF_MAP.get(name)
                if target in ALLOWED and not looks_secret(value):
                    cursor = db.execute("INSERT OR IGNORE INTO preferences(name,value,updated_at) "
                                        "VALUES(?,?,strftime('%s','now'))", (target, str(value)[:200]))
                    report["preferences"] += cursor.rowcount or 0
        if "automations" in tables:
            imported = []
            for name, trigger, tool, args, enabled in legacy.execute(
                    "SELECT name, trigger_text, tool_name, arguments, enabled FROM automations"):
                cursor = db.execute("INSERT OR IGNORE INTO automations(name,trigger_text,tool_name,arguments,enabled) "
                                    "VALUES(?,?,?,?,?)", (name, trigger, LEGACY_TOOLS.get(tool, tool), args, enabled))
                if cursor.rowcount:
                    imported.append(name)
                    report["automations"] += 1
            if imported:
                _remember_legacy(db, imported)
    finally:
        legacy.close()
    db.set_meta("legacy_jarvis_imported", str(report))
    log.info("dados do JARVIS importados: %s", report)
    return report


def import_copilot_settings(db: Database, path: Path | None) -> dict:
    """Lê uma única vez o ``copilot.json`` do JARVIS original (ao lado do ``assistant.sqlite3``) e devolve
    as exclusões do Observador para somar às do usuário. O arquivo original nunca é alterado."""
    if path is None or not Path(path).is_file() or db.get_meta("legacy_copilot_imported"):
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("copilot.json do JARVIS original ilegível: %s", exc)
        return {}
    excluded = []
    if isinstance(data, dict) and isinstance(data.get("excluded"), list):
        excluded = [str(x).strip()[:60] for x in data["excluded"] if str(x).strip()][:50]
    db.set_meta("legacy_copilot_imported", json.dumps({"excluded": len(excluded)}))
    return {"excluded": excluded}
