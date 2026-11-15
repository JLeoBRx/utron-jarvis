"""Auditoria administrativa: quem fez o quê, quando e de onde. Nunca registra senha, token ou corpo de conteúdo."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.models import AuditEvent, User, as_utc


def record(db: Session, action: str, *, actor_id: int | None = None, target_type: str = "", target_id: object = "",
           detail: dict[str, Any] | None = None, ip: str = "") -> None:
    db.add(AuditEvent(actor_id=actor_id, action=action, target_type=target_type, target_id=str(target_id),
                      detail=detail or {}, ip=ip[:64]))


def recent(db: Session, *, limit: int = 50, before_id: int | None = None, actor_id: int | None = None) -> list[dict]:
    query = (select(AuditEvent, User.name).outerjoin(User, User.id == AuditEvent.actor_id)
             .order_by(AuditEvent.id.desc()).limit(min(max(limit, 1), 200)))
    if before_id:
        query = query.where(AuditEvent.id < before_id)
    if actor_id is not None:
        query = query.where(AuditEvent.actor_id == actor_id)
    return [{"id": event.id, "action": event.action, "actor": name or "", "actor_id": event.actor_id,
             "target_type": event.target_type, "target_id": event.target_id, "detail": event.detail,
             "at": as_utc(event.at).isoformat()} for event, name in db.execute(query).all()]
