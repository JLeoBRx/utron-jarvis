"""Modelo de dados do Assistant (docs/architecture/DATA_MODEL.md). Banco privado e local; datas em UTC.

Nesta fase existe o modelo e a migração. Os serviços que gravam nestas tabelas chegam nas Fases 4 a 7.
Nenhuma tabela guarda segredo: provedores de IA referenciam a credencial pelo NOME dela no cofre do sistema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {"ix": "ix_%(table_name)s_%(column_0_N_name)s", "uq": "uq_%(table_name)s_%(column_0_N_name)s",
          "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}
Stamp = DateTime(timezone=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Setting(Base):
    """Configuração do aplicativo alterável em uso (a do processo vem de variáveis de ambiente)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class Preference(Base):
    """Preferência do usuário, declarada por ele ou aprendida (com a origem registrada)."""
    __tablename__ = "preferences"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")          # user | learned | import
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")         # active | archived
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(Stamp)


class AiProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)                             # local | remote
    base_url: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    default_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    allows_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)      # pode receber conteúdo privado?
    credential_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")      # NOME no cofre; nunca o segredo
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(Stamp)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)                             # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)    # de onde veio a resposta
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_kind_deleted_at", "kind", "deleted_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)        # fact | episode | procedure | note | reminder
    content: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="user")           # user | assistant | import
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)                                # exclusão lógica (lixeira)


class Tool(Base):
    __tablename__ = "tools"
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    risk: Mapped[str] = mapped_column(String(8), nullable=False, default="none")              # none | low | medium | high
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (Index("ix_tool_executions_status_requested_at", "status", "requested_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_name: Mapped[str] = mapped_column(ForeignKey("tools.name", ondelete="RESTRICT"), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verified: Mapped[bool | None] = mapped_column(Boolean)                                    # o efeito foi conferido?
    requested_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(Stamp)
    finished_at: Mapped[datetime | None] = mapped_column(Stamp)


class ActivityEvent(Base):
    """Histórico de atividades visível ao usuário: pedidos, ações, confirmações, falhas."""
    __tablename__ = "activity_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="done")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow, index=True)


class LogEvent(Base):
    """Eventos operacionais consultáveis pelo console (com retenção). O log completo fica em arquivo."""
    __tablename__ = "log_events"
    __table_args__ = (Index("ix_log_events_level_at", "level", "at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    component: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
