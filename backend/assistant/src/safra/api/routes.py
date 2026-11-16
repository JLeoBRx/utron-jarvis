"""Rotas locais usadas pela interface principal e pelo console (só em 127.0.0.1).

Toda rota aqui lê ou grava dados reais do banco privado. O que ainda não existe no Assistant — gateway de IA,
executor de ferramentas, voz — é informado como "não implementado" pelas rotas de estado; nada é simulado.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from safra_foundation import migrations
from safra_foundation.database import sqlite_path

from .. import __version__
from .. import ai_gateway, api, communication, core, intelligence, memory, monitoring, platform, projects, security, storage, tools, voice
from ..ai_gateway.status import UNAVAILABLE, gateway_status
from ..memory import conversations, memories, preferences
from ..monitoring import activity
from ..projects import service as project_service
from ..storage import MIGRATIONS
from ..storage.db import transaction
from ..storage.models import Conversation, Memory, Message, Project
from ..tools import catalog

router = APIRouter(prefix="/api/v1")
MODULES = {"core": core, "storage": storage, "security": security, "monitoring": monitoring, "platform": platform,
           "memory": memory, "ai_gateway": ai_gateway, "voice": voice, "communication": communication, "projects": projects,
           "tools": tools, "intelligence": intelligence, "api": api}


@contextmanager
def _db(request: Request) -> Iterator[Session]:
    with transaction(request.app.state.session_factory) as db:
        yield db


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ sistema (console)
@router.get("/system/status", tags=["sistema"], summary="Estado do Assistant, dos módulos e do banco")
def system_status(request: Request) -> dict[str, Any]:
    settings, engine = request.app.state.settings, request.app.state.engine
    report = request.app.state.health.report()
    database = sqlite_path(settings.database_url)
    with _db(request) as db:
        counts = {"conversations": db.scalar(select(func.count()).select_from(Conversation)) or 0,
                  "messages": db.scalar(select(func.count()).select_from(Message)) or 0,
                  "memories": db.scalar(select(func.count()).select_from(Memory).where(Memory.deleted_at.is_(None))) or 0,
                  "projects": db.scalar(select(func.count()).select_from(Project)) or 0}
    return {
        "service": "assistant", "version": __version__, "environment": settings.environment,
        "started_at": request.app.state.started_at,
        "health": report.as_dict(),
        "database": {"file": database.name if database else None,
                     "revision": migrations.current_revision(engine, MIGRATIONS),
                     "head": migrations.head_revision(MIGRATIONS),
                     "size_bytes": database.stat().st_size if database and database.is_file() else None,
                     "counts": counts},
        "modules": [{"name": name, **module.STATUS} for name, module in MODULES.items()],
        "ai": UNAVAILABLE,
        "voice": {"situacao": "nao_implementado", "fase": 6},
    }


@router.get("/system/resources", tags=["sistema"], summary="Uso de recursos medido agora")
def system_resources(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return request.app.state.resources.sample(data_dir=settings.data_dir, database=sqlite_path(settings.database_url))


@router.get("/system/settings", tags=["sistema"], summary="Configuração do processo (só leitura)")
def system_settings(request: Request) -> dict[str, Any]:
    s = request.app.state.settings
    return {"environment": s.environment, "data_dir": str(s.data_dir), "api_host": s.api_host, "api_port": s.api_port,
            "log_level": s.log_level, "log_to_file": s.log_to_file, "migrate_on_start": s.migrate_on_start,
            "editable": False,
            "note": "A configuração do processo vem das variáveis SAFRA_* e muda ao reiniciar. Preferências ficam no banco."}


@router.get("/activity", tags=["sistema"], summary="Atividades recentes")
def recent_activity(request: Request, limit: int = Query(30, ge=1, le=200), kind: str | None = None) -> list[dict[str, Any]]:
    with _db(request) as db:
        return activity.recent(db, limit=limit, kind=kind)


# ------------------------------------------------------------------ conversas
class ConversationIn(_Body):
    title: str = Field("", max_length=conversations.TITLE_MAX)
    project_id: int | None = None


class ConversationPatch(_Body):
    title: str | None = Field(None, max_length=conversations.TITLE_MAX)
    project_id: int | None = None
    archived: bool | None = None


class MessageIn(_Body):
    content: str = Field(min_length=1, max_length=conversations.CONTENT_MAX)


@router.get("/conversations", tags=["conversas"])
def list_conversations(request: Request, q: str = Query("", max_length=200), archived: bool = False,
                       project_id: int | None = None, limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    with _db(request) as db:
        return conversations.list_conversations(db, query=q, archived=archived, project_id=project_id, limit=limit)


@router.post("/conversations", tags=["conversas"], status_code=201)
def create_conversation(request: Request, body: ConversationIn) -> dict[str, Any]:
    with _db(request) as db:
        created = conversations.create_conversation(db, title=body.title, project_id=body.project_id)
        activity.record(db, "conversa", "Conversa criada", ref_type="conversation", ref_id=created["id"])
        return created


@router.get("/conversations/{conversation_id}", tags=["conversas"])
def get_conversation(request: Request, conversation_id: int) -> dict[str, Any]:
    with _db(request) as db:
        return conversations.get_conversation(db, conversation_id)


@router.patch("/conversations/{conversation_id}", tags=["conversas"])
def update_conversation(request: Request, conversation_id: int, body: ConversationPatch) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    with _db(request) as db:
        updated = conversations.update_conversation(db, conversation_id, changes)
        if "archived" in changes:
            activity.record(db, "conversa", "Conversa arquivada" if changes["archived"] else "Conversa desarquivada",
                            ref_type="conversation", ref_id=conversation_id)
        return updated


@router.post("/conversations/{conversation_id}/messages", tags=["conversas"], status_code=201)
def send_message(request: Request, conversation_id: int, body: MessageIn) -> dict[str, Any]:
    """Grava a mensagem. A resposta vem marcada como indisponível: não existe gateway de IA nesta fase."""
    with _db(request) as db:
        message = conversations.add_user_message(db, conversation_id, body.content)
        activity.record(db, "pedido", "Pedido sem resposta: o gateway de IA não foi implementado", state="indisponivel",
                        ref_type="conversation", ref_id=conversation_id)
        return {"message": message,
                "reply": {"status": "indisponivel", "code": "gateway_ia_nao_implementado", "message": UNAVAILABLE["mensagem"]}}


# ------------------------------------------------------------------ projetos
class ProjectIn(_Body):
    name: str = Field(min_length=1, max_length=project_service.NAME_MAX)
    description: str = Field("", max_length=project_service.DESCRIPTION_MAX)


class ProjectPatch(_Body):
    name: str | None = Field(None, min_length=1, max_length=project_service.NAME_MAX)
    description: str | None = Field(None, max_length=project_service.DESCRIPTION_MAX)
    status: Literal["active", "archived"] | None = None


@router.get("/projects", tags=["projetos"])
def list_projects(request: Request, status: Literal["active", "archived"] | None = None) -> list[dict[str, Any]]:
    with _db(request) as db:
        return project_service.list_projects(db, status=status)


@router.post("/projects", tags=["projetos"], status_code=201)
def create_project(request: Request, body: ProjectIn) -> dict[str, Any]:
    with _db(request) as db:
        created = project_service.create_project(db, name=body.name, description=body.description)
        activity.record(db, "projeto", f"Projeto criado: {created['name']}", ref_type="project", ref_id=created["id"])
        return created


@router.get("/projects/{project_id}", tags=["projetos"])
def get_project(request: Request, project_id: int) -> dict[str, Any]:
    with _db(request) as db:
        return project_service.get_project(db, project_id)


@router.patch("/projects/{project_id}", tags=["projetos"])
def update_project(request: Request, project_id: int, body: ProjectPatch) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    with _db(request) as db:
        updated = project_service.update_project(db, project_id, changes)
        if "status" in changes:
            title = "Projeto arquivado" if changes["status"] == "archived" else "Projeto reativado"
            activity.record(db, "projeto", f"{title}: {updated['name']}", ref_type="project", ref_id=project_id)
        return updated


# ------------------------------------------------------------------ memória
MemoryKind = Literal["fact", "episode", "procedure", "note", "reminder"]


class MemoryIn(_Body):
    kind: MemoryKind = "note"
    content: str = Field(min_length=1, max_length=memories.CONTENT_MAX)
    project_id: int | None = None
    importance: int = Field(0, ge=0, le=3)


class MemoryPatch(_Body):
    kind: MemoryKind | None = None
    content: str | None = Field(None, min_length=1, max_length=memories.CONTENT_MAX)
    project_id: int | None = None
    importance: int | None = Field(None, ge=0, le=3)


@router.get("/memories", tags=["memória"])
def list_memories(request: Request, kind: MemoryKind | None = None, q: str = Query("", max_length=200),
                  project_id: int | None = None, trash: bool = False) -> list[dict[str, Any]]:
    with _db(request) as db:
        return memories.list_memories(db, kind=kind, query=q, project_id=project_id, trash=trash)


@router.post("/memories", tags=["memória"], status_code=201)
def create_memory(request: Request, body: MemoryIn) -> dict[str, Any]:
    with _db(request) as db:
        created = memories.create_memory(db, body.model_dump())
        activity.record(db, "memoria", f"{created['kind_label']} registrado na memória", ref_type="memory", ref_id=created["id"])
        return created


@router.patch("/memories/{memory_id}", tags=["memória"])
def update_memory(request: Request, memory_id: int, body: MemoryPatch) -> dict[str, Any]:
    with _db(request) as db:
        return memories.update_memory(db, memory_id, body.model_dump(exclude_unset=True))


@router.delete("/memories/{memory_id}", tags=["memória"], summary="Move para a lixeira (exclusão lógica)")
def trash_memory(request: Request, memory_id: int) -> dict[str, Any]:
    with _db(request) as db:
        moved = memories.move_to_trash(db, memory_id)
        activity.record(db, "memoria", "Memória movida para a lixeira", ref_type="memory", ref_id=memory_id)
        return moved


@router.post("/memories/{memory_id}/restore", tags=["memória"])
def restore_memory(request: Request, memory_id: int) -> dict[str, Any]:
    with _db(request) as db:
        restored = memories.restore(db, memory_id)
        activity.record(db, "memoria", "Memória restaurada da lixeira", ref_type="memory", ref_id=memory_id)
        return restored


# ------------------------------------------------------------------ preferências
class PreferenceIn(_Body):
    value: bool | str


@router.get("/preferences", tags=["preferências"])
def get_preferences(request: Request) -> dict[str, Any]:
    with _db(request) as db:
        return preferences.get_preferences(db)


@router.put("/preferences/{key}", tags=["preferências"])
def set_preference(request: Request, key: str, body: PreferenceIn) -> dict[str, Any]:
    with _db(request) as db:
        saved = preferences.set_preference(db, key, body.value)
        activity.record(db, "preferencia", f"Preferência alterada: {saved['label']}", ref_type="preference", ref_id=key)
        return saved


# ------------------------------------------------------------------ inteligência artificial e ferramentas
@router.get("/ai/status", tags=["ia"], summary="Estado do gateway de IA e provedores cadastrados")
def ai_status(request: Request) -> dict[str, Any]:
    with _db(request) as db:
        return gateway_status(db)


@router.get("/tools", tags=["ferramentas"], summary="Ferramentas cadastradas e execuções registradas")
def tools_overview(request: Request) -> dict[str, Any]:
    with _db(request) as db:
        return catalog.overview(db)
