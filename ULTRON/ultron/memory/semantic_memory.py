"""Memória semântica: conhecimento (fatos sobre o usuário, o ambiente e o mundo)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .store import Database, clean_text


@dataclass
class Fact:
    id: int
    subject: str
    fact: str
    source: str
    confidence: float
    updated_at: float
    access_count: int

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _row(r) -> Fact:
    return Fact(r["id"], r["subject"], r["fact"], r["source"], r["confidence"], r["updated_at"], r["access_count"])


class SemanticMemory:
    def __init__(self, db: Database):
        self.db = db

    def remember(self, subject: str, fact: str, *, source: str = "user", confidence: float = 1.0) -> Fact:
        subject = clean_text(subject, 80, field="assunto")
        fact = clean_text(fact, 600, field="fato")
        now = time.time()
        self.db.execute(
            "INSERT INTO facts(subject,fact,source,confidence,created_at,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(subject) DO UPDATE SET fact=excluded.fact, source=excluded.source, "
            "confidence=excluded.confidence, updated_at=excluded.updated_at",
            (subject, fact, source, max(0.0, min(1.0, confidence)), now, now))
        return self.get(subject)  # type: ignore[return-value]

    def get(self, subject: str) -> Fact | None:
        row = self.db.one("SELECT * FROM facts WHERE lower(subject)=lower(?)", (subject,))
        return _row(row) if row else None

    def forget(self, subject: str) -> bool:
        cursor = self.db.execute("DELETE FROM facts WHERE lower(subject)=lower(?)", (subject,))
        return cursor.rowcount > 0

    def touch(self, ids: list[int]) -> None:
        now = time.time()
        for fid in ids:
            self.db.execute("UPDATE facts SET access_count=access_count+1, last_access=? WHERE id=?", (now, fid))

    def candidates(self, terms: list[str], limit: int = 200) -> list[Fact]:
        if not terms:
            rows = self.db.query("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (min(limit, 50),))
        else:
            clauses = " OR ".join(["lower(subject) LIKE ? OR lower(fact) LIKE ?"] * len(terms))
            params: list[Any] = []
            for t in terms:
                params += [f"%{t}%", f"%{t}%"]
            rows = self.db.query(f"SELECT * FROM facts WHERE {clauses} ORDER BY updated_at DESC LIMIT ?",
                                 params + [limit])
        return [_row(r) for r in rows]

    def all(self, limit: int = 500) -> list[Fact]:
        return [_row(r) for r in self.db.query("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,))]

    def count(self) -> int:
        row = self.db.one("SELECT COUNT(*) FROM facts")
        return int(row[0]) if row else 0
