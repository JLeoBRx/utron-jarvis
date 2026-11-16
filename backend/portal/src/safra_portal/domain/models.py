"""Modelo de dados do Portal (docs/architecture/DATA_MODEL.md). Todas as datas são UTC com fuso."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Index, Integer, MetaData, String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {"ix": "ix_%(table_name)s_%(column_0_N_name)s", "uq": "uq_%(table_name)s_%(column_0_N_name)s",
          "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s", "pk": "pk_%(table_name)s"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """O SQLite devolve datas sem fuso; todas foram gravadas em UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


Stamp = DateTime(timezone=True)


class Role(Base):
    __tablename__ = "roles"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)


class Permission(Base):
    __tablename__ = "permissions"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role_key: Mapped[str] = mapped_column(ForeignKey("roles.key"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(Stamp)
    last_login_at: Mapped[datetime | None] = mapped_column(Stamp)
    password_changed_at: Mapped[datetime | None] = mapped_column(Stamp)
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(Stamp)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    user: Mapped[User] = relationship(lazy="joined")


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(Stamp, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(Stamp)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)


class Media(Base):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stored_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(200), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    alt_text: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)


class Content(Base):
    """Página ou notícia. Os campos daqui são o RASCUNHO corrente; o que o público vê é a versão publicada."""
    __tablename__ = "contents"
    __table_args__ = (UniqueConstraint("type", "slug"), Index("ix_contents_type_status", "type", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)                 # page | news
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    seo_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    seo_description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    cover_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")   # draft | published
    published_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_versions.id", ondelete="SET NULL", use_alter=True, name="fk_contents_published_version"))
    published_at: Mapped[datetime | None] = mapped_column(Stamp)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ContentVersion(Base):
    """Cada gravação gera uma versão imutável. Publicar aponta para uma delas."""
    __tablename__ = "content_versions"
    __table_args__ = (UniqueConstraint("content_id", "number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    seo_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    seo_description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    cover_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="save")       # save | restore | seed
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class PublicationEvent(Base):
    __tablename__ = "publication_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("content_versions.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(16), nullable=False)      # create | publish | unpublish | restore | delete
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow, index=True)


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("version", "platform"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    platform: Mapped[str] = mapped_column(String(24), nullable=False, default="windows")
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="experimental")  # stable | beta | experimental
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(Stamp)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(Stamp)


class ReleaseFile(Base):
    """Arquivo de instalação de uma versão. A tabela existe; o envio e a publicação estão bloqueados (AD-17)."""
    __tablename__ = "release_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow, index=True)


class SiteSetting(Base):
    """Configurações PÚBLICAS do site (página inicial, rodapé, contato). Nunca segredos."""
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(Stamp, nullable=False, default=utcnow)
