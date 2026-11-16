"""Páginas e notícias: rascunho, versões imutáveis, publicação, restauração e exclusão lógica.

Regra central: os campos de `Content` são o RASCUNHO; o público só recebe o que está na versão apontada por
`published_version_id` de um conteúdo publicado e não excluído. As funções `public_*` são o único caminho de
leitura usado pelo site público.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import Conflict, InvalidInput, NotFound

from ..domain import blocks as blocks_module
from ..domain.models import Category, Content, ContentVersion, Media, PublicationEvent, User, as_utc, utcnow
from . import audit

TYPES = ("page", "news")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_PAGE_SLUGS = frozenset({"admin", "api", "static", "media", "healthz", "sitemap.xml", "robots.txt", "inicio",
                                 "index", "favicon.ico"})


@dataclass(frozen=True)
class Draft:
    """Dados editáveis de um conteúdo, já validados."""
    title: str
    summary: str
    blocks: list[dict]
    seo_title: str
    seo_description: str
    cover_media_id: int | None
    category_id: int | None


def _check_type(content_type: str) -> None:
    if content_type not in TYPES:
        raise InvalidInput("Tipo de conteúdo inexistente.")


def check_slug(content_type: str, slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not _SLUG.match(slug) or len(slug) > 80:
        raise InvalidInput("O endereço (slug) aceita letras minúsculas, números e hífens, até 80 caracteres.",
                           details={"field": "slug"})
    if content_type == "page" and slug in RESERVED_PAGE_SLUGS:
        raise InvalidInput("Este endereço é reservado pelo sistema.", details={"field": "slug"})
    return slug


def validate_draft(db: Db, data: dict[str, Any]) -> Draft:
    title = str(data.get("title", "")).strip()
    if not 1 <= len(title) <= 200:
        raise InvalidInput("Informe o título (até 200 caracteres).", details={"field": "title"})
    summary = str(data.get("summary", "")).strip()
    seo_title = str(data.get("seo_title", "")).strip()
    seo_description = str(data.get("seo_description", "")).strip()
    for field, value, limit in (("summary", summary, 500), ("seo_title", seo_title, 200),
                                ("seo_description", seo_description, 300)):
        if len(value) > limit:
            raise InvalidInput(f"O campo ficou longo demais (máximo {limit} caracteres).", details={"field": field})
    try:
        blocks = blocks_module.validate_blocks(data.get("blocks", []))
    except ValidationError as exc:
        problems = [{"field": "blocks." + ".".join(str(p) for p in err["loc"]), "problem": err["msg"]}
                    for err in exc.errors()[:10]]
        raise InvalidInput("O conteúdo tem blocos inválidos.", details={"fields": problems}) from None
    cover = data.get("cover_media_id") or None
    category = data.get("category_id") or None
    wanted_media = blocks_module.media_ids(blocks) | ({int(cover)} if cover else set())
    if wanted_media:
        found = set(db.scalars(select(Media.id).where(Media.id.in_(wanted_media), Media.deleted_at.is_(None))))
        if found != wanted_media:
            raise InvalidInput("O conteúdo usa uma imagem que não existe na biblioteca.", details={"field": "blocks"})
    if category and not db.scalar(select(Category.id).where(Category.id == int(category), Category.deleted_at.is_(None))):
        raise InvalidInput("Categoria inexistente.", details={"field": "category_id"})
    return Draft(title, summary, blocks, seo_title, seo_description, int(cover) if cover else None,
                 int(category) if category else None)


def _event(db: Db, content: Content, action: str, actor_id: int | None, version_id: int | None = None) -> None:
    db.add(PublicationEvent(content_id=content.id, version_id=version_id, action=action, actor_id=actor_id))


def _new_version(db: Db, content: Content, *, actor_id: int | None, kind: str = "save", note: str = "") -> ContentVersion:
    number = (db.scalar(select(func.max(ContentVersion.number)).where(ContentVersion.content_id == content.id)) or 0) + 1
    version = ContentVersion(content_id=content.id, number=number, title=content.title, summary=content.summary,
                             blocks=content.blocks, seo_title=content.seo_title, seo_description=content.seo_description,
                             cover_media_id=content.cover_media_id, category_id=content.category_id, kind=kind,
                             note=note[:200], created_by=actor_id)
    db.add(version)
    db.flush()
    return version


def _apply(content: Content, draft: Draft) -> None:
    content.title, content.summary, content.blocks = draft.title, draft.summary, draft.blocks
    content.seo_title, content.seo_description = draft.seo_title, draft.seo_description
    content.cover_media_id, content.category_id = draft.cover_media_id, draft.category_id


def get(db: Db, content_type: str, content_id: int) -> Content:
    _check_type(content_type)
    content = db.get(Content, content_id)
    if content is None or content.type != content_type or content.deleted_at is not None:
        raise NotFound("Conteúdo não encontrado.")
    return content


def create(db: Db, content_type: str, data: dict[str, Any], *, actor_id: int | None, ip: str = "",
           kind: str = "save") -> Content:
    _check_type(content_type)
    slug = check_slug(content_type, str(data.get("slug", "")))
    if db.scalar(select(Content.id).where(Content.type == content_type, Content.slug == slug)):
        raise Conflict("Já existe um conteúdo com este endereço.", details={"field": "slug"})
    draft = validate_draft(db, data)
    content = Content(type=content_type, slug=slug, status="draft", created_by=actor_id, updated_by=actor_id)
    _apply(content, draft)
    db.add(content)
    db.flush()
    version = _new_version(db, content, actor_id=actor_id, kind=kind)
    _event(db, content, "create", actor_id, version.id)
    audit.record(db, f"{content_type}.create", actor_id=actor_id, target_type=content_type, target_id=content.id,
                 detail={"slug": slug}, ip=ip)
    return content


def save_draft(db: Db, content_type: str, content_id: int, data: dict[str, Any], *, lock_version: int,
               actor_id: int | None, ip: str = "") -> Content:
    """Grava o rascunho como versão nova. Se outra pessoa gravou antes, recusa em vez de sobrescrever."""
    content = get(db, content_type, content_id)
    if lock_version != content.lock_version:
        editor = db.scalar(select(User.name).where(User.id == content.updated_by)) or ""
        raise Conflict("Este conteúdo foi alterado por outra pessoa depois que você o abriu. Recarregue antes de gravar.",
                       details={"current_lock_version": content.lock_version, "updated_by": editor})
    if "slug" in data and data["slug"] != content.slug:
        slug = check_slug(content_type, str(data["slug"]))
        if db.scalar(select(Content.id).where(Content.type == content_type, Content.slug == slug, Content.id != content.id)):
            raise Conflict("Já existe um conteúdo com este endereço.", details={"field": "slug"})
        content.slug = slug
    _apply(content, validate_draft(db, data))
    content.lock_version += 1
    content.updated_by, content.updated_at = actor_id, utcnow()
    version = _new_version(db, content, actor_id=actor_id, note=str(data.get("note", "")))
    audit.record(db, f"{content_type}.save", actor_id=actor_id, target_type=content_type, target_id=content.id,
                 detail={"version": version.number}, ip=ip)
    return content


def latest_version(db: Db, content: Content) -> ContentVersion:
    return db.scalar(select(ContentVersion).where(ContentVersion.content_id == content.id)
                     .order_by(ContentVersion.number.desc()).limit(1))


def publish(db: Db, content_type: str, content_id: int, *, actor_id: int | None, ip: str = "") -> Content:
    """Torna pública a versão mais recente."""
    content = get(db, content_type, content_id)
    version = latest_version(db, content)
    content.published_version_id, content.status = version.id, "published"
    content.published_at = content.published_at or utcnow()
    content.updated_at = utcnow()
    _event(db, content, "publish", actor_id, version.id)
    audit.record(db, f"{content_type}.publish", actor_id=actor_id, target_type=content_type, target_id=content.id,
                 detail={"version": version.number}, ip=ip)
    return content


def unpublish(db: Db, content_type: str, content_id: int, *, actor_id: int | None, ip: str = "") -> Content:
    content = get(db, content_type, content_id)
    if content.status == "published":
        _event(db, content, "unpublish", actor_id, content.published_version_id)
        audit.record(db, f"{content_type}.unpublish", actor_id=actor_id, target_type=content_type,
                     target_id=content.id, ip=ip)
    content.published_version_id, content.status, content.updated_at = None, "draft", utcnow()
    return content


def versions(db: Db, content: Content) -> list[dict]:
    rows = db.execute(select(ContentVersion, User.name).outerjoin(User, User.id == ContentVersion.created_by)
                      .where(ContentVersion.content_id == content.id).order_by(ContentVersion.number.desc())).all()
    return [{"id": v.id, "number": v.number, "title": v.title, "kind": v.kind, "note": v.note, "author": name or "",
             "created_at": as_utc(v.created_at).isoformat(), "published": v.id == content.published_version_id}
            for v, name in rows]


def get_version(db: Db, content: Content, version_id: int) -> ContentVersion:
    version = db.get(ContentVersion, version_id)
    if version is None or version.content_id != content.id:
        raise NotFound("Versão não encontrada.")
    return version


def restore(db: Db, content_type: str, content_id: int, version_id: int, *, actor_id: int | None, ip: str = "") -> Content:
    """Traz uma versão antiga de volta COMO RASCUNHO (versão nova). Não publica: publicar é outra permissão."""
    content = get(db, content_type, content_id)
    old = get_version(db, content, version_id)
    content.title, content.summary, content.blocks = old.title, old.summary, old.blocks
    content.seo_title, content.seo_description = old.seo_title, old.seo_description
    content.cover_media_id, content.category_id = old.cover_media_id, old.category_id
    content.lock_version += 1
    content.updated_by, content.updated_at = actor_id, utcnow()
    version = _new_version(db, content, actor_id=actor_id, kind="restore", note=f"restaurada da versão {old.number}")
    _event(db, content, "restore", actor_id, version.id)
    audit.record(db, f"{content_type}.restore", actor_id=actor_id, target_type=content_type, target_id=content.id,
                 detail={"from_version": old.number, "new_version": version.number}, ip=ip)
    return content


def delete(db: Db, content_type: str, content_id: int, *, confirm_slug: str, actor_id: int | None, ip: str = "") -> None:
    """Exclusão lógica, com confirmação: é preciso repetir o endereço do conteúdo."""
    content = get(db, content_type, content_id)
    if confirm_slug != content.slug:
        raise InvalidInput("Para excluir, confirme digitando o endereço (slug) do conteúdo.",
                           details={"field": "confirm_slug"})
    original = content.slug
    content.status, content.published_version_id = "draft", None
    content.deleted_at, content.updated_at = utcnow(), utcnow()
    content.slug = f"{original[:60]}--excluido-{content.id}"        # libera o endereço para um conteúdo novo
    _event(db, content, "delete", actor_id)
    audit.record(db, f"{content_type}.delete", actor_id=actor_id, target_type=content_type, target_id=content.id,
                 detail={"slug": original}, ip=ip)


def list_admin(db: Db, content_type: str, *, status: str = "", search: str = "") -> list[Content]:
    _check_type(content_type)
    query = select(Content).where(Content.type == content_type, Content.deleted_at.is_(None))
    if status in ("draft", "published"):
        query = query.where(Content.status == status)
    if search:
        query = query.where(func.lower(Content.title).contains(search.strip().lower()[:80]))
    return list(db.scalars(query.order_by(Content.updated_at.desc()).limit(500)))


def has_unpublished_changes(db: Db, content: Content) -> bool:
    if content.status != "published":
        return False
    return latest_version(db, content).id != content.published_version_id


# ---------------------------------------------------------------------- leitura pública
@dataclass(frozen=True)
class Published:
    """O que o visitante pode ver: os dados da VERSÃO PUBLICADA, nunca o rascunho."""
    id: int
    type: str
    slug: str
    title: str
    summary: str
    blocks: list[dict]
    seo_title: str
    seo_description: str
    cover_media_id: int | None
    category_id: int | None
    published_at: Any
    updated_at: Any


def _published_query():
    return (select(Content, ContentVersion)
            .join(ContentVersion, ContentVersion.id == Content.published_version_id)
            .where(Content.status == "published", Content.deleted_at.is_(None)))


def _published(content: Content, version: ContentVersion) -> Published:
    return Published(content.id, content.type, content.slug, version.title, version.summary, version.blocks,
                     version.seo_title, version.seo_description, version.cover_media_id, version.category_id,
                     as_utc(content.published_at), as_utc(version.created_at))


def public_get(db: Db, content_type: str, slug: str) -> Published | None:
    row = db.execute(_published_query().where(Content.type == content_type, Content.slug == slug)).first()
    return _published(*row) if row else None


def public_list(db: Db, content_type: str, *, limit: int = 20, offset: int = 0,
                category_id: int | None = None) -> list[Published]:
    query = _published_query().where(Content.type == content_type)
    if category_id:
        query = query.where(ContentVersion.category_id == category_id)
    rows = db.execute(query.order_by(Content.published_at.desc(), Content.id.desc()).limit(limit).offset(offset)).all()
    return [_published(*row) for row in rows]


def public_count(db: Db, content_type: str) -> int:
    return db.scalar(select(func.count()).select_from(Content).where(
        Content.type == content_type, Content.status == "published", Content.deleted_at.is_(None))) or 0
