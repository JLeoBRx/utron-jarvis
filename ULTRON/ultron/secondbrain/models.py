"""Modelo de dados do Second Brain."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

KINDS: dict[str, str] = {
    "task": "Tarefa", "event": "Compromisso", "study": "Estudo", "project": "Projeto", "idea": "Ideia",
    "note": "Nota", "person": "Pessoa", "routine": "Rotina", "deadline": "Prazo",
}
KIND_PLURALS: dict[str, str] = {
    "task": "Tarefas", "event": "Compromissos", "study": "Estudos", "project": "Projetos", "idea": "Ideias",
    "note": "Notas", "person": "Pessoas", "routine": "Rotinas", "deadline": "Prazos",
}
STATUSES = ("open", "in_progress", "waiting", "done", "cancelled")
STATUS_LABELS = {"open": "aberto", "in_progress": "em andamento", "waiting": "aguardando", "done": "concluído",
                 "cancelled": "cancelado"}
PRIORITIES = {1: "baixa", 2: "normal", 3: "alta", 4: "urgente"}
RELATIONS = {"depends_on": "depende de", "related": "relacionado a", "part_of": "parte de", "about": "sobre"}
ORIGINS = ("user", "hub", "voice", "text", "auto", "import", "system")
ACTIONABLE = ("task", "event", "study", "deadline", "routine")     # podem ser concluídos, ter prazo e lembrete


@dataclass
class Record:
    id: str
    kind: str
    title: str
    body: str = ""
    status: str = "open"
    priority: int = 2
    due_local: str = ""             # horário de parede "YYYY-MM-DD HH:MM" (vazio = sem data)
    due_at: float | None = None     # instante absoluto (epoch)
    all_day: bool = False
    end_local: str = ""
    tz: str = ""
    recurrence: str = ""
    project_id: str | None = None
    tags: list = field(default_factory=list)
    origin: str = "user"
    origin_detail: str = ""
    confirmed: bool = True          # False = inferido (captura automática aguardando revisão)
    confidence: float = 1.0
    data: dict = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float | None = None
    archived_at: float | None = None
    deleted_at: float | None = None

    @property
    def label(self) -> str:
        return KINDS.get(self.kind, "Registro")

    @property
    def is_open(self) -> bool:
        return self.status in ("open", "in_progress", "waiting") and not self.deleted_at and not self.archived_at

    def overdue(self, now: float) -> bool:
        if not self.is_open or self.due_at is None or self.kind not in ACTIONABLE:
            return False
        limit = self.due_at + (86400 if self.all_day else 0)       # dia inteiro: atrasa no fim do dia
        return now > limit

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["label"] = self.label
        return data

    @classmethod
    def from_row(cls, row) -> "Record":
        return cls(
            id=row["id"], kind=row["kind"], title=row["title"], body=row["body"], status=row["status"],
            priority=int(row["priority"]), due_local=row["due_local"] or "", due_at=row["due_at"],
            all_day=bool(row["all_day"]), end_local=row["end_local"] or "", tz=row["tz"] or "",
            recurrence=row["recurrence"] or "", project_id=row["project_id"],
            tags=_json(row["tags"], []), origin=row["origin"], origin_detail=row["origin_detail"] or "",
            confirmed=bool(row["confirmed"]), confidence=float(row["confidence"]), data=_json(row["data"], {}),
            created_at=row["created_at"], updated_at=row["updated_at"], completed_at=row["completed_at"],
            archived_at=row["archived_at"], deleted_at=row["deleted_at"])


@dataclass
class Reminder:
    id: str
    record_id: str
    at_local: str
    tz: str
    next_at: float
    leads: list = field(default_factory=list)       # minutos de antecedência
    recurrence: str = ""
    anchor_day: int | None = None
    status: str = "scheduled"                      # scheduled | done | cancelled
    snoozed_until: float | None = None
    repeats: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    last_fired_at: float | None = None
    pinned: bool = False                           # horário próprio ("lembre-me disso às 18h"): não segue o prazo

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "Reminder":
        return cls(id=row["id"], record_id=row["record_id"], at_local=row["at_local"], tz=row["tz"] or "",
                   next_at=float(row["next_at"]), leads=[int(x) for x in _json(row["leads"], [])],
                   recurrence=row["recurrence"] or "", anchor_day=row["anchor_day"], status=row["status"],
                   snoozed_until=row["snoozed_until"], repeats=int(row["repeats"]), created_at=row["created_at"],
                   updated_at=row["updated_at"], last_fired_at=row["last_fired_at"],
                   pinned=bool(row["pinned"]) if "pinned" in row.keys() else False)


def _json(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default
