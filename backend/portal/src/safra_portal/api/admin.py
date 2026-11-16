"""Rotas do painel administrativo (`/admin/api`). Toda rota, exceto as de entrada, declara a permissão exigida
com `require(...)`; tests/test_authorization.py percorre todas elas com cada papel e sem sessão."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import InvalidInput, NotFound

from ..auth.deps import (COOKIE_PATH, SESSION_COOKIE, check_origin, client_ip, current_identity, get_auth, get_db,
                         require)
from ..auth.service import AuthService, Identity
from ..cms import audit, content, homepage, releases
from ..domain import permissions
from ..domain.models import Category, Content, Media, Session, User, as_utc, utcnow
from ..media.service import MediaService, to_dict as media_dict

router = APIRouter(prefix="/admin/api")
PUBLIC_ROUTES = frozenset({("POST", "/admin/api/auth/login"), ("POST", "/admin/api/auth/recover")})
SESSION_ONLY_ROUTES = frozenset({("GET", "/admin/api/auth/session"), ("POST", "/admin/api/auth/logout")})


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(_In):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class RecoverIn(_In):
    token: str = Field(max_length=200)
    new_password: str = Field(max_length=256)


class PasswordIn(_In):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class ContentIn(_In):
    slug: str = Field(max_length=80)
    title: str = Field(max_length=200)
    summary: str = Field(default="", max_length=500)
    blocks: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    seo_title: str = Field(default="", max_length=200)
    seo_description: str = Field(default="", max_length=300)
    cover_media_id: int | None = None
    category_id: int | None = None


class ContentSaveIn(ContentIn):
    lock_version: int = Field(ge=1)
    note: str = Field(default="", max_length=200)


class DeleteIn(_In):
    confirm_slug: str = Field(max_length=120)


class CategoryIn(_In):
    slug: str = Field(max_length=80)
    name: str = Field(min_length=1, max_length=80)


class MediaPatchIn(_In):
    alt_text: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=64)


class ReleaseIn(_In):
    version: str = Field(max_length=40)
    platform: Literal["windows"] = "windows"
    channel: Literal["stable", "beta", "experimental"] = "experimental"
    notes: str = Field(default="", max_length=8000)


class UserIn(_In):
    email: str = Field(max_length=254)
    name: str = Field(max_length=120)
    role: str = Field(max_length=32)


class UserPatchIn(_In):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


def _media(request: Request) -> MediaService:
    return request.app.state.media


def _identity_dict(identity: Identity) -> dict[str, Any]:
    return {"user": {"id": identity.user_id, "email": identity.email, "name": identity.name, "role": identity.role,
                     "role_name": permissions.ROLES.get(identity.role, identity.role)},
            "permissions": sorted(identity.permissions), "csrf_token": identity.csrf_token}


def _user_dict(user: User) -> dict[str, Any]:
    locked = user.locked_until is not None and as_utc(user.locked_until) > utcnow()
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role_key,
            "role_name": permissions.ROLES.get(user.role_key, user.role_key), "is_active": user.is_active,
            "has_password": bool(user.password_hash), "locked": locked,
            "last_login_at": as_utc(user.last_login_at).isoformat() if user.last_login_at else None}


def _content_dict(db: Db, item: Content, *, full: bool = True) -> dict[str, Any]:
    plural = "pages" if item.type == "page" else "news"
    public_path = f"/{item.slug}" if item.type == "page" else f"/atualizacoes/{item.slug}"
    data: dict[str, Any] = {
        "id": item.id, "type": item.type, "slug": item.slug, "title": item.title, "summary": item.summary,
        "status": item.status, "lock_version": item.lock_version, "category_id": item.category_id,
        "cover_media_id": item.cover_media_id,
        "published_at": as_utc(item.published_at).isoformat() if item.published_at else None,
        "updated_at": as_utc(item.updated_at).isoformat(),
        "has_unpublished_changes": content.has_unpublished_changes(db, item),
        "public_path": public_path if item.status == "published" else None,
        "preview_path": f"/admin/preview/{plural}/{item.id}",
    }
    if full:
        data.update(blocks=item.blocks, seo_title=item.seo_title, seo_description=item.seo_description)
    return data


# ------------------------------------------------------------------------- entrada e sessão
@router.post("/auth/login", tags=["entrada"])
def login(body: LoginIn, request: Request, response: Response, db: Db = Depends(get_db),
          auth: AuthService = Depends(get_auth)) -> dict[str, Any]:
    check_origin(request)
    token, session = auth.login(db, email=body.email, password=body.password, ip=client_ip(request),
                                user_agent=request.headers.get("user-agent", ""))
    settings = request.app.state.settings
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_absolute_hours * 3600, path=COOKIE_PATH,
                        httponly=True, secure=settings.secure_cookies, samesite="strict")
    db.commit()
    identity = auth.identify(db, token)
    return _identity_dict(identity)


@router.post("/auth/recover", tags=["entrada"])
def recover(body: RecoverIn, request: Request, db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    check_origin(request)
    auth.recover(db, token=body.token, new_password=body.new_password, ip=client_ip(request))
    return {"ok": True}


@router.get("/auth/session", tags=["entrada"])
def session_info(identity: Identity = Depends(current_identity)) -> dict[str, Any]:
    return _identity_dict(identity)


@router.post("/auth/logout", tags=["entrada"])
def logout(request: Request, response: Response, identity: Identity = Depends(current_identity),
           db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    auth.logout(db, identity, client_ip(request))
    response.delete_cookie(SESSION_COOKIE, path=COOKIE_PATH)
    return {"ok": True}


@router.post("/auth/password", tags=["entrada"])
def change_password(body: PasswordIn, request: Request, identity: Identity = Depends(require("admin.access")),
                    db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    auth.change_password(db, identity, current=body.current, new=body.new, ip=client_ip(request))
    return {"ok": True}


@router.get("/sessions", tags=["entrada"])
def my_sessions(identity: Identity = Depends(require("admin.access")), db: Db = Depends(get_db),
                auth: AuthService = Depends(get_auth)) -> list[dict]:
    return [{"id": s.id, "current": s.id == identity.session_id, "ip": s.ip, "user_agent": s.user_agent,
             "created_at": as_utc(s.created_at).isoformat(), "last_seen_at": as_utc(s.last_seen_at).isoformat()}
            for s in auth.list_sessions(db, identity.user_id)]


@router.delete("/sessions/{session_id}", tags=["entrada"])
def revoke_session(session_id: int, identity: Identity = Depends(require("admin.access")), db: Db = Depends(get_db)) -> dict:
    row = db.get(Session, session_id)
    if row is None or row.user_id != identity.user_id:              # só as próprias sessões
        raise NotFound("Sessão não encontrada.")
    row.revoked_at = utcnow()
    return {"ok": True}


# ------------------------------------------------------------------------- painel
@router.get("/dashboard", tags=["painel"])
def dashboard(identity: Identity = Depends(require("dashboard.read")), db: Db = Depends(get_db)) -> dict[str, Any]:
    def count(content_type: str, status: str) -> int:
        return db.scalar(select(func.count()).select_from(Content).where(
            Content.type == content_type, Content.status == status, Content.deleted_at.is_(None))) or 0

    recent = db.scalars(select(Content).where(Content.deleted_at.is_(None)).order_by(Content.updated_at.desc()).limit(8))
    data = {
        "pages": {"published": count("page", "published"), "draft": count("page", "draft")},
        "news": {"published": count("news", "published"), "draft": count("news", "draft")},
        "media": db.scalar(select(func.count()).select_from(Media).where(Media.deleted_at.is_(None))) or 0,
        "recent_changes": [_content_dict(db, item, full=False) for item in recent],
        "activity": audit.recent(db, limit=10, actor_id=None if identity.can("audit.read") else identity.user_id),
        "downloads_blocked": not releases.RELEASE_PUBLICATION_ENABLED,
    }
    return data


# ------------------------------------------------------------------------- páginas e notícias
def _register_content(plural: str, content_type: str) -> None:
    tag = "páginas" if content_type == "page" else "notícias"

    @router.get(f"/{plural}", tags=[tag], name=f"list_{plural}")
    def list_items(status: str = "", q: str = "", _: Identity = Depends(require("content.read")),
                   db: Db = Depends(get_db)) -> list[dict]:
        return [_content_dict(db, item, full=False) for item in content.list_admin(db, content_type, status=status, search=q)]

    @router.post(f"/{plural}", tags=[tag], status_code=201, name=f"create_{plural}")
    def create_item(body: ContentIn, request: Request, identity: Identity = Depends(require("content.edit")),
                    db: Db = Depends(get_db)) -> dict:
        item = content.create(db, content_type, body.model_dump(), actor_id=identity.user_id, ip=client_ip(request))
        return _content_dict(db, item)

    @router.get(f"/{plural}/{{item_id}}", tags=[tag], name=f"get_{plural}")
    def get_item(item_id: int, _: Identity = Depends(require("content.read")), db: Db = Depends(get_db)) -> dict:
        return _content_dict(db, content.get(db, content_type, item_id))

    @router.put(f"/{plural}/{{item_id}}", tags=[tag], name=f"save_{plural}")
    def save_item(item_id: int, body: ContentSaveIn, request: Request,
                  identity: Identity = Depends(require("content.edit")), db: Db = Depends(get_db)) -> dict:
        data = body.model_dump()
        item = content.save_draft(db, content_type, item_id, data, lock_version=data.pop("lock_version"),
                                  actor_id=identity.user_id, ip=client_ip(request))
        return _content_dict(db, item)

    @router.post(f"/{plural}/{{item_id}}/publish", tags=[tag], name=f"publish_{plural}")
    def publish_item(item_id: int, request: Request, identity: Identity = Depends(require("content.publish")),
                     db: Db = Depends(get_db)) -> dict:
        item = content.publish(db, content_type, item_id, actor_id=identity.user_id, ip=client_ip(request))
        return _content_dict(db, item)

    @router.post(f"/{plural}/{{item_id}}/unpublish", tags=[tag], name=f"unpublish_{plural}")
    def unpublish_item(item_id: int, request: Request, identity: Identity = Depends(require("content.publish")),
                       db: Db = Depends(get_db)) -> dict:
        item = content.unpublish(db, content_type, item_id, actor_id=identity.user_id, ip=client_ip(request))
        return _content_dict(db, item)

    @router.get(f"/{plural}/{{item_id}}/versions", tags=[tag], name=f"versions_{plural}")
    def list_versions(item_id: int, _: Identity = Depends(require("content.read")), db: Db = Depends(get_db)) -> list[dict]:
        return content.versions(db, content.get(db, content_type, item_id))

    @router.get(f"/{plural}/{{item_id}}/versions/{{version_id}}", tags=[tag], name=f"version_{plural}")
    def get_version(item_id: int, version_id: int, _: Identity = Depends(require("content.read")),
                    db: Db = Depends(get_db)) -> dict:
        version = content.get_version(db, content.get(db, content_type, item_id), version_id)
        return {"id": version.id, "number": version.number, "title": version.title, "summary": version.summary,
                "blocks": version.blocks, "seo_title": version.seo_title, "seo_description": version.seo_description,
                "kind": version.kind, "note": version.note, "created_at": as_utc(version.created_at).isoformat()}

    @router.post(f"/{plural}/{{item_id}}/versions/{{version_id}}/restore", tags=[tag], name=f"restore_{plural}")
    def restore_version(item_id: int, version_id: int, request: Request,
                        identity: Identity = Depends(require("content.edit")), db: Db = Depends(get_db)) -> dict:
        item = content.restore(db, content_type, item_id, version_id, actor_id=identity.user_id, ip=client_ip(request))
        return _content_dict(db, item)

    @router.delete(f"/{plural}/{{item_id}}", tags=[tag], name=f"delete_{plural}")
    def delete_item(item_id: int, body: DeleteIn, request: Request,
                    identity: Identity = Depends(require("content.delete")), db: Db = Depends(get_db)) -> dict:
        content.delete(db, content_type, item_id, confirm_slug=body.confirm_slug, actor_id=identity.user_id,
                       ip=client_ip(request))
        return {"ok": True}


_register_content("pages", "page")
_register_content("news", "news")


# ------------------------------------------------------------------------- categorias
def _category_dict(category: Category) -> dict:
    return {"id": category.id, "slug": category.slug, "name": category.name}


@router.get("/categories", tags=["notícias"])
def list_categories(_: Identity = Depends(require("content.read")), db: Db = Depends(get_db)) -> list[dict]:
    return [_category_dict(c) for c in db.scalars(select(Category).where(Category.deleted_at.is_(None)).order_by(Category.name))]


@router.post("/categories", tags=["notícias"], status_code=201)
def create_category(body: CategoryIn, request: Request, identity: Identity = Depends(require("categories.manage")),
                    db: Db = Depends(get_db)) -> dict:
    slug = content.check_slug("news", body.slug)
    if db.scalar(select(Category.id).where(Category.slug == slug)):
        raise InvalidInput("Já existe uma categoria com este endereço.", details={"field": "slug"})
    category = Category(slug=slug, name=body.name.strip())
    db.add(category)
    db.flush()
    audit.record(db, "category.create", actor_id=identity.user_id, target_type="category", target_id=category.id,
                 ip=client_ip(request))
    return _category_dict(category)


@router.put("/categories/{category_id}", tags=["notícias"])
def update_category(category_id: int, body: CategoryIn, request: Request,
                    identity: Identity = Depends(require("categories.manage")), db: Db = Depends(get_db)) -> dict:
    category = db.get(Category, category_id)
    if category is None or category.deleted_at is not None:
        raise NotFound("Categoria não encontrada.")
    slug = content.check_slug("news", body.slug)
    if db.scalar(select(Category.id).where(Category.slug == slug, Category.id != category.id)):
        raise InvalidInput("Já existe uma categoria com este endereço.", details={"field": "slug"})
    category.slug, category.name = slug, body.name.strip()
    audit.record(db, "category.update", actor_id=identity.user_id, target_type="category", target_id=category.id,
                 ip=client_ip(request))
    return _category_dict(category)


@router.delete("/categories/{category_id}", tags=["notícias"])
def delete_category(category_id: int, request: Request, identity: Identity = Depends(require("categories.manage")),
                    db: Db = Depends(get_db)) -> dict:
    category = db.get(Category, category_id)
    if category is None or category.deleted_at is not None:
        raise NotFound("Categoria não encontrada.")
    category.deleted_at = utcnow()
    category.slug = f"{category.slug[:50]}--excluida-{category.id}"
    audit.record(db, "category.delete", actor_id=identity.user_id, target_type="category", target_id=category.id,
                 ip=client_ip(request))
    return {"ok": True}


# ------------------------------------------------------------------------- mídia
@router.get("/media", tags=["mídia"])
def list_media(request: Request, category: str = "", _: Identity = Depends(require("media.read")),
               db: Db = Depends(get_db)) -> list[dict]:
    return [media_dict(m) for m in _media(request).list(db, category=category)]


@router.post("/media", tags=["mídia"], status_code=201)
async def upload_media(request: Request, filename: str = "", alt_text: str = "", category: str = "",
                       identity: Identity = Depends(require("media.upload")), db: Db = Depends(get_db)) -> dict:
    """Corpo = bytes do arquivo. O tamanho é limitado enquanto se lê; o tipo é decidido pelo conteúdo."""
    service = _media(request)
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > service.max_bytes:
        raise InvalidInput(f"O arquivo passa do limite de {service.max_bytes // 1024} KiB.", details={"field": "file"})
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > service.max_bytes:
            raise InvalidInput(f"O arquivo passa do limite de {service.max_bytes // 1024} KiB.", details={"field": "file"})
        chunks.append(chunk)
    media = await run_in_threadpool(service.store, db, b"".join(chunks), original_name=filename, alt_text=alt_text,
                                    category=category, actor_id=identity.user_id, ip=client_ip(request))
    return media_dict(media)


@router.get("/media/{media_id}/usage", tags=["mídia"])
def media_usage(media_id: int, request: Request, _: Identity = Depends(require("media.read")),
                db: Db = Depends(get_db)) -> dict:
    service = _media(request)
    service.get(db, media_id)
    return {"used_in": service.usage(db, media_id)}


@router.patch("/media/{media_id}", tags=["mídia"])
def update_media(media_id: int, body: MediaPatchIn, request: Request,
                 identity: Identity = Depends(require("media.upload")), db: Db = Depends(get_db)) -> dict:
    return media_dict(_media(request).update(db, media_id, alt_text=body.alt_text, category=body.category,
                                              actor_id=identity.user_id, ip=client_ip(request)))


@router.delete("/media/{media_id}", tags=["mídia"])
def delete_media(media_id: int, request: Request, identity: Identity = Depends(require("media.delete")),
                 db: Db = Depends(get_db)) -> dict:
    _media(request).remove(db, media_id, actor_id=identity.user_id, ip=client_ip(request))
    return {"ok": True}


# ------------------------------------------------------------------------- página inicial e dados do site
@router.get("/homepage", tags=["página inicial"])
def get_homepage(_: Identity = Depends(require("content.read")), db: Db = Depends(get_db)) -> dict:
    return homepage.load(db, homepage.HOMEPAGE_KEY)


@router.put("/homepage", tags=["página inicial"])
def put_homepage(body: dict[str, Any], request: Request, identity: Identity = Depends(require("homepage.edit")),
                 db: Db = Depends(get_db)) -> dict:
    return homepage.save(db, homepage.HOMEPAGE_KEY, body, actor_id=identity.user_id, ip=client_ip(request))


@router.get("/site", tags=["página inicial"])
def get_site(_: Identity = Depends(require("content.read")), db: Db = Depends(get_db)) -> dict:
    return homepage.load(db, homepage.SITE_KEY)


@router.put("/site", tags=["página inicial"])
def put_site(body: dict[str, Any], request: Request, identity: Identity = Depends(require("homepage.edit")),
             db: Db = Depends(get_db)) -> dict:
    return homepage.save(db, homepage.SITE_KEY, body, actor_id=identity.user_id, ip=client_ip(request))


# ------------------------------------------------------------------------- downloads
@router.get("/releases", tags=["downloads"])
def list_releases(_: Identity = Depends(require("releases.manage")), db: Db = Depends(get_db)) -> dict:
    return {"publication_enabled": releases.RELEASE_PUBLICATION_ENABLED, "block_reason": releases.BLOCK_REASON,
            "items": [releases.to_dict(r) for r in releases.list_admin(db)]}


@router.post("/releases", tags=["downloads"], status_code=201)
def create_release(body: ReleaseIn, request: Request, identity: Identity = Depends(require("releases.manage")),
                   db: Db = Depends(get_db)) -> dict:
    return releases.to_dict(releases.create(db, body.model_dump(), actor_id=identity.user_id, ip=client_ip(request)))


@router.put("/releases/{release_id}", tags=["downloads"])
def update_release(release_id: int, body: ReleaseIn, request: Request,
                   identity: Identity = Depends(require("releases.manage")), db: Db = Depends(get_db)) -> dict:
    return releases.to_dict(releases.update(db, release_id, body.model_dump(), actor_id=identity.user_id,
                                            ip=client_ip(request)))


@router.post("/releases/{release_id}/publish", tags=["downloads"])
def publish_release(release_id: int, request: Request, identity: Identity = Depends(require("releases.manage")),
                    db: Db = Depends(get_db)) -> dict:
    return releases.to_dict(releases.publish(db, release_id, actor_id=identity.user_id, ip=client_ip(request)))


@router.delete("/releases/{release_id}", tags=["downloads"])
def delete_release(release_id: int, request: Request, identity: Identity = Depends(require("releases.manage")),
                   db: Db = Depends(get_db)) -> dict:
    releases.remove(db, release_id, actor_id=identity.user_id, ip=client_ip(request))
    return {"ok": True}


# ------------------------------------------------------------------------- usuários e auditoria
@router.get("/users", tags=["usuários"])
def list_users(_: Identity = Depends(require("users.manage")), db: Db = Depends(get_db),
               auth: AuthService = Depends(get_auth)) -> dict:
    return {"roles": [{"key": key, "name": name, "permissions": sorted(permissions.MATRIX[key])}
                      for key, name in permissions.ROLES.items()],
            "items": [_user_dict(u) for u in auth.list_users(db)]}


@router.post("/users", tags=["usuários"], status_code=201)
def create_user(body: UserIn, request: Request, identity: Identity = Depends(require("users.manage")),
                db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    """A conta nasce sem senha. Quem a criou recebe, uma única vez, o código para o dono definir a senha."""
    user = auth.create_user(db, email=body.email, name=body.name, role=body.role, actor_id=identity.user_id,
                            ip=client_ip(request))
    token = auth.create_recovery_token(db, user.id, actor_id=identity.user_id, ip=client_ip(request))
    return {"user": _user_dict(user), "recovery_token": token}


@router.patch("/users/{user_id}", tags=["usuários"])
def update_user(user_id: int, body: UserPatchIn, request: Request, identity: Identity = Depends(require("users.manage")),
                db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    return _user_dict(auth.update_user(db, user_id, name=body.name, role=body.role, is_active=body.is_active,
                                       actor_id=identity.user_id, ip=client_ip(request)))


@router.post("/users/{user_id}/recovery-token", tags=["usuários"])
def recovery_token(user_id: int, request: Request, identity: Identity = Depends(require("users.manage")),
                   db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> dict:
    return {"recovery_token": auth.create_recovery_token(db, user_id, actor_id=identity.user_id, ip=client_ip(request))}


@router.get("/audit", tags=["auditoria"])
def list_audit(limit: int = 50, before_id: int | None = None, _: Identity = Depends(require("audit.read")),
               db: Db = Depends(get_db)) -> list[dict]:
    return audit.recent(db, limit=limit, before_id=before_id)
