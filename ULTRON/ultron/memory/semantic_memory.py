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

    def candidates(self, terms: list[str], limit: int = 200, scan: int = 5000) -> list[Fact]:
        """Fatos que contêm algum dos termos — SEM acento dos dois lados ("medico" acha "médico").

        O filtro antigo (``LIKE`` no SQL) comparava o termo sem acento com o texto acentuado e perdia fatos
        como "médico da família" (medido no protocolo PV-03). A comparação agora é feita na mesma
        normalização dos termos, sobre os ``scan`` fatos mais recentes (volume de uma máquina pessoal)."""
        if not terms:
            rows = self.db.query("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (min(limit, 50),))
            return [_row(r) for r in rows]
        from .retrieval import _matches, terms as split_terms
        wanted = [t for t in terms if t]
        out: list[Fact] = []
        for r in self.db.query("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (scan,)):
            words = set(split_terms(f"{r['subject']} {r['fact']}", 256))
            if any(_matches(t, words) for t in wanted):
                out.append(_row(r))
                if len(out) >= limit:
                    break
        return out

    def all(self, limit: int = 500) -> list[Fact]:
        return [_row(r) for r in self.db.query("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,))]

    def count(self) -> int:
        row = self.db.one("SELECT COUNT(*) FROM facts")
        return int(row[0]) if row else 0
