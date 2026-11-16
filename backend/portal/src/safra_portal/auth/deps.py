"""Dependências do FastAPI que protegem o painel: sessão, origem, anti-CSRF e permissão por rota."""
from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session as Db

from safra_foundation.errors import Forbidden, NotAuthenticated, OriginRefused
from safra_foundation.tokens import constant_time_equals

from ..domain.permissions import PERMISSIONS
from .service import AuthService, Identity

SESSION_COOKIE = "safra_portal_session"
COOKIE_PATH = "/admin"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_db(request: Request) -> Iterator[Db]:
    """Uma transação por pedido: confirma se a rota terminar bem, desfaz se lançar."""
    db: Db = request.app.state.session_factory()
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def get_auth(request: Request) -> AuthService:
    return request.app.state.auth


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def check_origin(request: Request) -> None:
    """Pedidos que alteram precisam vir do próprio site (defesa contra CSRF, somada ao cookie SameSite=Strict)."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin", "")
    if origin not in request.app.state.settings.allowed_origins:
        raise OriginRefused()


def current_identity(request: Request, db: Db = Depends(get_db), auth: AuthService = Depends(get_auth)) -> Identity:
    check_origin(request)
    identity = auth.identify(db, request.cookies.get(SESSION_COOKIE))
    if identity is None:
        raise NotAuthenticated()
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not constant_time_equals(sent, identity.csrf_token):
            raise Forbidden("O pedido não trouxe o código anti-CSRF da sessão.", details={"reason": "csrf"})
    request.state.identity = identity
    return identity


def require(permission: str) -> Callable[..., Identity]:
    """Dependência que exige ``permission``. O atributo ``permission`` permite ao teste percorrer todas as rotas."""
    if permission not in PERMISSIONS:
        raise ValueError(f"permissão desconhecida: {permission}")

    def dependency(identity: Identity = Depends(current_identity)) -> Identity:
        if not identity.can("admin.access") or not identity.can(permission):
            raise Forbidden(details={"permission": permission})
        return identity

    dependency.permission = permission                            # type: ignore[attr-defined]
    return dependency
