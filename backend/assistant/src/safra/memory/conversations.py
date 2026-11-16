"""Conversas e mensagens. Grava e consulta; não gera respostas — isso é do gateway de IA (Fase 5)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from safra_foundation import errors

from ..storage.models import Conversation, Message, Project, utcnow

TITLE_MAX = 200
CONTENT_MAX = 20_000
PREVIEW = 140


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def message_dict(message: Message) -> dict[str, Any]:
    return {"id": message.id, "role": message.role, "content": message.content, "provenance": message.provenance,
            "provider_id": message.provider_id, "created_at": _iso(message.created_at)}


def _summary(db: Session, conversation: Conversation) -> dict[str, Any]:
    count = db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conversation.id)) or 0
    last = db.scalar(select(Message).where(Message.conversation_id == conversation.id)
                     .order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
    return {"id": conversation.id, "title": conversation.title or "Conversa sem título", "project_id": conversation.project_id,
            "started_at": _iso(conversation.started_at), "updated_at": _iso(conversation.updated_at),
            "archived": conversation.archived_at is not None, "message_count": count,
            "preview": (last.content[:PREVIEW] if last else "")}


def _get(db: Session, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise errors.NotFound("A conversa não existe.")
    return conversation


def _check_project(db: Session, project_id: int | None) -> None:
    if project_id is not None and db.get(Project, project_id) is None:
        raise errors.InvalidInput("O projeto indicado não existe.", details={"fields": [{"field": "project_id", "problem": "não existe"}]})


def list_conversations(db: Session, *, query: str = "", archived: bool = False, project_id: int | None = None,
                       limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(Conversation).where(Conversation.archived_at.is_not(None) if archived else Conversation.archived_at.is_(None))
    if project_id is not None:
        stmt = stmt.where(Conversation.project_id == project_id)
    if query.strip():
        like = f"%{query.strip().lower()}%"
        in_messages = select(Message.conversation_id).where(func.lower(Message.content).like(like))
        stmt = stmt.where(or_(func.lower(Conversation.title).like(like), Conversation.id.in_(in_messages)))
    stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(max(1, min(limit, 200)))
    return [_summary(db, c) for c in db.scalars(stmt)]


def create_conversation(db: Session, *, title: str = "", project_id: int | None = None) -> dict[str, Any]:
    _check_project(db, project_id)
    conversation = Conversation(title=title.strip()[:TITLE_MAX], project_id=project_id)
    db.add(conversation)
    db.flush()
    return _summary(db, conversation)


def get_conversation(db: Session, conversation_id: int) -> dict[str, Any]:
    conversation = _get(db, conversation_id)
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                          .order_by(Message.created_at, Message.id))
    return {**_summary(db, conversation), "messages": [message_dict(m) for m in messages]}


def update_conversation(db: Session, conversation_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    conversation = _get(db, conversation_id)
    if "title" in changes:
        conversation.title = str(changes["title"]).strip()[:TITLE_MAX]
    if "project_id" in changes:
        _check_project(db, changes["project_id"])
        conversation.project_id = changes["project_id"]
    if "archived" in changes:
        conversation.archived_at = utcnow() if changes["archived"] else None
    conversation.updated_at = utcnow()
    db.flush()
    return _summary(db, conversation)


def add_user_message(db: Session, conversation_id: int, content: str) -> dict[str, Any]:
    """Grava a mensagem do usuário. Se a conversa não tem título, o início da mensagem vira o título."""
    text = content.strip()
    if not text:
        raise errors.InvalidInput("A mensagem está vazia.")
    if len(text) > CONTENT_MAX:
        raise errors.InvalidInput(f"A mensagem passa de {CONTENT_MAX} caracteres.")
    conversation = _get(db, conversation_id)
    if conversation.archived_at is not None:
        raise errors.Conflict("A conversa está arquivada. Desarquive para escrever nela.")
    message = Message(conversation_id=conversation_id, role="user", content=text, provenance={"origem": "interface"})
    db.add(message)
    if not conversation.title:
        conversation.title = (text[:57] + "…") if len(text) > 60 else text
    conversation.updated_at = utcnow()
    db.flush()
    return message_dict(message)
