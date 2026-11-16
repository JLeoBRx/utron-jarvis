"""Projetos: criar, editar, arquivar e ver o que está ligado a cada um (conversas e memórias)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from safra_foundation import errors

from ..storage.models import Conversation, Memory, Project, utcnow

NAME_MAX = 120
DESCRIPTION_MAX = 2_000


def _dict(db: Session, project: Project) -> dict[str, Any]:
    conversations = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.project_id == project.id)) or 0
    memories = db.scalar(select(func.count()).select_from(Memory)
                         .where(Memory.project_id == project.id, Memory.deleted_at.is_(None))) or 0
    return {"id": project.id, "name": project.name, "description": project.description, "status": project.status,
            "created_at": project.created_at.isoformat(), "updated_at": project.updated_at.isoformat(),
            "archived_at": project.archived_at.isoformat() if project.archived_at else None,
            "conversation_count": conversations, "memory_count": memories}


def _get(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise errors.NotFound("O projeto não existe.")
    return project


def _clean_name(db: Session, name: str, current_id: int | None = None) -> str:
    name = name.strip()
    if not name or len(name) > NAME_MAX:
        raise errors.InvalidInput(f"O nome precisa ter de 1 a {NAME_MAX} caracteres.")
    clash = db.scalar(select(Project).where(func.lower(Project.name) == name.lower()))
    if clash is not None and clash.id != current_id:
        raise errors.Conflict("Já existe um projeto com esse nome.")
    return name


def list_projects(db: Session, *, status: str | None = None) -> list[dict[str, Any]]:
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    return [_dict(db, p) for p in db.scalars(stmt.order_by(Project.status, Project.updated_at.desc()))]


def create_project(db: Session, *, name: str, description: str = "") -> dict[str, Any]:
    if len(description) > DESCRIPTION_MAX:
        raise errors.InvalidInput("A descrição é longa demais.")
    project = Project(name=_clean_name(db, name), description=description.strip())
    db.add(project)
    db.flush()
    return _dict(db, project)


def get_project(db: Session, project_id: int) -> dict[str, Any]:
    return _dict(db, _get(db, project_id))


def update_project(db: Session, project_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    project = _get(db, project_id)
    if "name" in changes:
        project.name = _clean_name(db, str(changes["name"]), project.id)
    if "description" in changes:
        if len(str(changes["description"])) > DESCRIPTION_MAX:
            raise errors.InvalidInput("A descrição é longa demais.")
        project.description = str(changes["description"]).strip()
    if "status" in changes:
        if changes["status"] not in ("active", "archived"):
            raise errors.InvalidInput("Estado do projeto desconhecido.")
        project.status = changes["status"]
        project.archived_at = utcnow() if changes["status"] == "archived" else None
    project.updated_at = utcnow()
    db.flush()
    return _dict(db, project)
