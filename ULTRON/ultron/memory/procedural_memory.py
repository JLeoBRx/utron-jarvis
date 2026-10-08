"""Memória procedural: como executar procedimentos.

Duas origens:

* ``learned``: sequências de ações que levaram a objetivos verificados;
* ``automation``: automações do usuário disparadas por frase exata (compatível com o JARVIS).

Uma sequência só é reutilizada se a taxa de sucesso continuar alta.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

from .store import Database, clean_text, dumps, loads

_STOP = {"o", "a", "os", "as", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "um", "uma",
         "para", "por", "com", "que", "meu", "minha", "me", "por favor", "ultron", "senhor"}


def fingerprint(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = re.sub(r"\d+", "#", value)
    words = [w for w in re.findall(r"[a-z#][a-z#_\-.]+", value) if w not in _STOP]
    return " ".join(words[:16])


def similarity(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class Procedure:
    id: int
    name: str
    trigger: str
    steps: list
    source: str
    success_count: int
    failure_count: int
    enabled: bool
    last_used: float | None

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["success_rate"] = self.success_rate
        return data


def _row(r) -> Procedure:
    return Procedure(r["id"], r["name"], r["trigger"], loads(r["steps"], []), r["source"], r["success_count"],
                     r["failure_count"], bool(r["enabled"]), r["last_used"])


class ProceduralMemory:
    MIN_RATE = 0.6

    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ procedimentos aprendidos
    def learn(self, goal_text: str, steps: list[dict], *, success: bool, name: str | None = None) -> Procedure | None:
        trigger = fingerprint(goal_text)
        if not trigger or not steps:
            return None
        name = (name or trigger)[:80]
        existing = self.db.one("SELECT * FROM procedures WHERE trigger=? AND source='learned'", (trigger,))
        now = time.time()
        if existing:
            column = "success_count" if success else "failure_count"
            self.db.execute(f"UPDATE procedures SET {column}={column}+1, last_used=?, steps=CASE WHEN ? THEN ? ELSE steps END "
                            "WHERE id=?", (now, int(success), dumps(steps), existing["id"]))
        else:
            if not success:
                return None              # só procedimentos que funcionaram viram memória
            self.db.execute("INSERT OR IGNORE INTO procedures(name,trigger,steps,source,success_count,created_at,last_used) "
                            "VALUES(?,?,?,?,?,?,?)", (name, trigger, dumps(steps), "learned", 1, now, now))
        row = self.db.one("SELECT * FROM procedures WHERE trigger=? AND source='learned'", (trigger,))
        return _row(row) if row else None

    def match(self, goal_text: str, *, threshold: float = 0.75) -> Procedure | None:
        target = fingerprint(goal_text)
        best, best_score = None, 0.0
        for row in self.db.query("SELECT * FROM procedures WHERE enabled=1 AND source='learned'"):
            proc = _row(row)
            score = similarity(target, proc.trigger)
            if score > best_score:
                best, best_score = proc, score
        if best and best_score >= threshold and best.success_rate >= self.MIN_RATE:
            return best
        return None

    def record_outcome(self, procedure_id: int, success: bool) -> None:
        column = "success_count" if success else "failure_count"
        self.db.execute(f"UPDATE procedures SET {column}={column}+1, last_used=? WHERE id=?", (time.time(), procedure_id))

    def all(self) -> list[Procedure]:
        return [_row(r) for r in self.db.query("SELECT * FROM procedures ORDER BY id")]

    def count(self) -> int:
        row = self.db.one("SELECT COUNT(*) FROM procedures")
        return int(row[0]) if row else 0

    # ------------------------------------------------------------ automações por frase exata
    @staticmethod
    def normalize_trigger(text: str) -> str:
        value = unicodedata.normalize("NFD", str(text or "").casefold())
        value = "".join(c for c in value if unicodedata.category(c) != "Mn")
        return " ".join(re.sub(r"[^\w\s]", " ", value).split())

    def save_automation(self, name: str, trigger: str, skill: str, arguments: dict) -> str:
        name = clean_text(name, 60, field="nome")
        normalized = self.normalize_trigger(clean_text(trigger, 100, field="frase"))
        if not normalized:
            raise ValueError("frase de ativação vazia")
        self.db.execute(
            "INSERT INTO automations(name,trigger_text,tool_name,arguments,enabled) VALUES(?,?,?,?,1) "
            "ON CONFLICT(name) DO UPDATE SET trigger_text=excluded.trigger_text, tool_name=excluded.tool_name, "
            "arguments=excluded.arguments, enabled=1", (name, normalized, skill, dumps(arguments)))
        return normalized

    def automation_for(self, text: str) -> dict | None:
        normalized = self.normalize_trigger(text)
        if not normalized:
            return None
        row = self.db.one("SELECT * FROM automations WHERE enabled=1 AND trigger_text=?", (normalized,))
        if not row:
            return None
        return {"name": row["name"], "trigger": row["trigger_text"], "skill": row["tool_name"],
                "arguments": loads(row["arguments"], {})}

    def automations(self) -> list[dict]:
        return [{"name": r["name"], "trigger": r["trigger_text"], "skill": r["tool_name"],
                 "arguments": loads(r["arguments"], {}), "enabled": bool(r["enabled"])}
                for r in self.db.query("SELECT * FROM automations ORDER BY name")]

    def set_automation_enabled(self, name: str, enabled: bool) -> bool:
        cursor = self.db.execute("UPDATE automations SET enabled=? WHERE lower(name)=lower(?)", (int(enabled), name))
        return cursor.rowcount > 0

    def delete_automation(self, name: str) -> bool:
        cursor = self.db.execute("DELETE FROM automations WHERE lower(name)=lower(?)", (name,))
        return cursor.rowcount > 0
