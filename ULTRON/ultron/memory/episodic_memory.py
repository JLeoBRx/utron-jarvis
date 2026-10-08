"""Memória episódica: experiências anteriores (o que foi tentado, o que aconteceu, evidências)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .store import Database, dumps, loads, looks_secret


@dataclass
class Episode:
    id: int
    kind: str
    summary: str
    goal_id: str | None
    actions: list
    outcome: str
    success: bool | None
    evidence: list
    context: dict
    started_at: float
    finished_at: float | None
    importance: float

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _row(row) -> Episode:
    success = None if row["success"] is None else bool(row["success"])
    return Episode(row["id"], row["kind"], row["summary"], row["goal_id"], loads(row["actions"], []),
                   row["outcome"], success, loads(row["evidence"], []), loads(row["context"], {}),
                   row["started_at"], row["finished_at"], row["importance"])


class EpisodicMemory:
    LIMIT = 5000

    def __init__(self, db: Database):
        self.db = db

    def record(self, kind: str, summary: str, *, goal_id: str | None = None, actions: list | None = None,
               outcome: str = "", success: bool | None = None, evidence: list | None = None,
               context: dict | None = None, started_at: float | None = None,
               importance: float = 0.5) -> int | None:
        summary = " ".join(str(summary or "").split())[:600]
        if not summary or looks_secret(summary):
            return None
        safe_evidence = [e for e in (evidence or []) if not looks_secret(e)][:20]
        cursor = self.db.execute(
            "INSERT INTO episodes(kind,goal_id,summary,actions,outcome,success,evidence,context,started_at,"
            "finished_at,importance) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (kind, goal_id, summary, dumps(actions or []), str(outcome)[:600],
             None if success is None else int(bool(success)), dumps(safe_evidence), dumps(context or {}),
             started_at or time.time(), time.time(), max(0.0, min(1.0, importance))))
        self.db.execute(f"DELETE FROM episodes WHERE id NOT IN (SELECT id FROM episodes ORDER BY id DESC LIMIT {self.LIMIT})")
        return int(cursor.lastrowid)

    def recent(self, limit: int = 10, kind: str | None = None) -> list[Episode]:
        if kind:
            rows = self.db.query("SELECT * FROM episodes WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
        else:
            rows = self.db.query("SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (limit,))
        return [_row(r) for r in rows]

    def candidates(self, terms: list[str], limit: int = 200) -> list[Episode]:
        if not terms:
            return self.recent(min(limit, 50))
        clauses = " OR ".join(["lower(summary) LIKE ?"] * len(terms))
        rows = self.db.query(f"SELECT * FROM episodes WHERE {clauses} ORDER BY id DESC LIMIT ?",
                             [f"%{t}%" for t in terms] + [limit])
        return [_row(r) for r in rows]

    def for_goal(self, goal_id: str) -> list[Episode]:
        return [_row(r) for r in self.db.query("SELECT * FROM episodes WHERE goal_id=? ORDER BY id", (goal_id,))]

    def count(self) -> int:
        row = self.db.one("SELECT COUNT(*) FROM episodes")
        return int(row[0]) if row else 0
