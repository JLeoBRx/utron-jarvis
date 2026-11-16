"""Histórico de atividades visível ao usuário. Grava o que aconteceu de fato; nunca o conteúdo privado inteiro."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import ActivityEvent


def record(db: Session, kind: str, title: str, *, origin: str = "interface", state: str = "done", ref_type: str = "",
           ref_id: str | int = "", detail: dict[str, Any] | None = None) -> None:
    db.add(ActivityEvent(kind=kind, origin=origin, title=title[:300], state=state, ref_type=ref_type,
                         ref_id=str(ref_id), detail=detail or {}))


def recent(db: Session, *, limit: int = 30, kind: str | None = None) -> list[dict[str, Any]]:
    stmt = select(ActivityEvent)
    if kind:
        stmt = stmt.where(ActivityEvent.kind == kind)
    rows = db.scalars(stmt.order_by(ActivityEvent.at.desc(), ActivityEvent.id.desc()).limit(max(1, min(limit, 200))))
    return [{"id": e.id, "kind": e.kind, "origin": e.origin, "title": e.title, "state": e.state, "ref_type": e.ref_type,
             "ref_id": e.ref_id, "at": e.at.isoformat()} for e in rows]
