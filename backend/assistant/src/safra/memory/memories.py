"""Memórias registradas pelo usuário: fatos, episódios, procedimentos, notas e lembretes. Exclusão vai para a lixeira."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from safra_foundation import errors

from ..storage.models import Memory, Project, utcnow

KINDS = {"fact": "Fato", "episode": "Episódio", "procedure": "Procedimento", "note": "Nota", "reminder": "Lembrete"}
CONTENT_MAX = 5_000


def memory_dict(memory: Memory) -> dict[str, Any]:
    return {"id": memory.id, "kind": memory.kind, "kind_label": KINDS.get(memory.kind, memory.kind), "content": memory.content,
            "project_id": memory.project_id, "source": memory.source, "importance": memory.importance,
            "created_at": memory.created_at.isoformat(), "updated_at": memory.updated_at.isoformat(),
            "deleted_at": memory.deleted_at.isoformat() if memory.deleted_at else None}


def _get(db: Session, memory_id: int) -> Memory:
    memory = db.get(Memory, memory_id)
    if memory is None:
        raise errors.NotFound("A memória não existe.")
    return memory


def _validate(db: Session, fields: dict[str, Any]) -> None:
    if "kind" in fields and fields["kind"] not in KINDS:
        raise errors.InvalidInput("Tipo de memória desconhecido.")
    if "content" in fields:
        text = str(fields["content"]).strip()
        if not text or len(text) > CONTENT_MAX:
            raise errors.InvalidInput(f"O conteúdo precisa ter de 1 a {CONTENT_MAX} caracteres.")
        fields["content"] = text
    if fields.get("project_id") is not None and db.get(Project, fields["project_id"]) is None:
        raise errors.InvalidInput("O projeto indicado não existe.")
    if "importance" in fields and not 0 <= int(fields["importance"]) <= 3:
        raise errors.InvalidInput("A importância vai de 0 a 3.")


def list_memories(db: Session, *, kind: str | None = None, query: str = "", project_id: int | None = None,
                  trash: bool = False, limit: int = 200) -> list[dict[str, Any]]:
    stmt = select(Memory).where(Memory.deleted_at.is_not(None) if trash else Memory.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(Memory.kind == kind)
    if project_id is not None:
        stmt = stmt.where(Memory.project_id == project_id)
    if query.strip():
        stmt = stmt.where(func.lower(Memory.content).like(f"%{query.strip().lower()}%"))
    stmt = stmt.order_by(Memory.importance.desc(), Memory.updated_at.desc()).limit(max(1, min(limit, 500)))
    return [memory_dict(m) for m in db.scalars(stmt)]


def create_memory(db: Session, fields: dict[str, Any]) -> dict[str, Any]:
    fields = {"kind": "note", "importance": 0, **fields}
    _validate(db, fields)
    memory = Memory(kind=fields["kind"], content=fields["content"], project_id=fields.get("project_id"),
                    importance=int(fields["importance"]), source="user", data={})
    db.add(memory)
    db.flush()
    return memory_dict(memory)


def update_memory(db: Session, memory_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    memory = _get(db, memory_id)
    if memory.deleted_at is not None:
        raise errors.Conflict("A memória está na lixeira. Restaure antes de editar.")
    _validate(db, fields)
    for key in ("kind", "content", "project_id", "importance"):
        if key in fields:
            setattr(memory, key, fields[key])
    memory.updated_at = utcnow()
    db.flush()
    return memory_dict(memory)


def move_to_trash(db: Session, memory_id: int) -> dict[str, Any]:
    memory = _get(db, memory_id)
    memory.deleted_at = memory.deleted_at or utcnow()
    db.flush()
    return memory_dict(memory)


def restore(db: Session, memory_id: int) -> dict[str, Any]:
    memory = _get(db, memory_id)
    memory.deleted_at = None
    memory.updated_at = utcnow()
    db.flush()
    return memory_dict(memory)
