"""Autorização conferida no servidor: cada rota do painel, sem sessão e com cada papel."""
import re

import pytest
from starlette.routing import Route

from safra_portal.api import admin as admin_api
from safra_portal.domain import permissions

from conftest import page_data


def _admin_routes(app=None):
    """Todas as rotas do painel, lidas do roteador do módulo (independe de como o FastAPI as embrulha no app)."""
    found = []
    for route in admin_api.router.routes:
        assert isinstance(route, Route) and route.path.startswith("/admin/api"), route
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found.append((method, route.path, route))
    assert len(found) >= 45, "a enumeração das rotas do painel voltou vazia ou incompleta"
    return found


def _permission(route) -> str | None:
    """Permissão declarada na rota por `require(...)`, procurada na árvore de dependências."""
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        permission = getattr(dependency.call, "permission", None)
        if permission:
            return permission
        stack.extend(dependency.dependencies)
    return None


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "999999", path)


def test_every_admin_route_declares_a_permission(portal):
    routes = _admin_routes(portal.app)
    undeclared = [(m, p) for m, p, r in routes if _permission(r) is None
                  and (m, p) not in admin_api.PUBLIC_ROUTES | admin_api.SESSION_ONLY_ROUTES]
    assert undeclared == []
    declared = {_permission(r) for _, _, r in routes} - {None}
    assert declared <= set(permissions.PERMISSIONS)
    assert declared == set(permissions.PERMISSIONS)                 # nenhuma permissão sem uso, nenhuma inventada


def test_the_enumerated_routes_are_the_ones_the_application_serves(portal):
    """Garante que o teste percorre as rotas reais: cada uma responde (401 sem sessão), nenhuma dá 404 de rota."""
    for method, path, _ in _admin_routes():
        response = portal.public.request(method, _concrete(path), json={}, headers={"Origin": portal.origin})
        assert response.status_code != 405, (method, path)
        if (method, path) not in admin_api.PUBLIC_ROUTES:
            assert response.status_code == 401, (method, path, response.status_code)


def test_a_visitor_reaches_no_admin_route(portal):
    """Critério 7: usuário público não acessa o CMS — nem lendo, nem alterando, nem com Origin correto."""
    for method, path, _ in _admin_routes(portal.app):
        if (method, path) in admin_api.PUBLIC_ROUTES:
            continue
        response = portal.public.request(method, _concrete(path), json={}, headers={"Origin": portal.origin})
        assert response.status_code == 401, (method, path, response.status_code)
        assert response.json()["error"]["code"] == "nao_autenticado"


@pytest.mark.parametrize("role", [permissions.EDITOR, permissions.PUBLICADOR, permissions.ADMINISTRADOR])
def test_each_role_is_refused_exactly_where_the_matrix_says(portal, role):
    session = portal.login(role)
    allowed = permissions.MATRIX[role]
    for method, path, route in _admin_routes(portal.app):
        permission = _permission(route)
        if permission is None:
            continue
        response = session.send(method, _concrete(path).removeprefix("/admin/api"), json={})
        if permission in allowed:
            assert response.status_code not in (401, 403), (role, method, path, response.status_code)
        else:
            assert response.status_code == 403, (role, method, path, response.status_code)
            assert response.json()["error"]["details"] == {"permission": permission}


def test_editor_cannot_manage_users_or_publish(portal):
    """Critério 8."""
    editor = portal.login("editor")
    assert editor.get("/users").status_code == 403
    assert editor.post("/users", json={"email": "x@exemplo.test", "name": "X", "role": "administrador"}).status_code == 403
    me = editor.session["user"]["id"]
    assert editor.patch(f"/users/{me}", json={"role": "administrador"}).status_code == 403     # não se promove
    assert editor.get("/audit").status_code == 403
    page = editor.post("/pages", json=page_data()).json()
    assert editor.post(f"/pages/{page['id']}/publish").status_code == 403
    assert editor.delete(f"/pages/{page['id']}", json={"confirm_slug": page["slug"]}).status_code == 403
    assert editor.put("/homepage", json={"title": "Invadido"}).status_code == 403


def test_publisher_can_publish_but_not_edit_or_manage(portal):
    """Critério 9."""
    editor = portal.login("editor")
    publisher = portal.login("publicador")
    page = editor.post("/pages", json=page_data()).json()
    assert publisher.post("/pages", json=page_data("outra")).status_code == 403
    assert publisher.put(f"/pages/{page['id']}", json={**page_data(), "lock_version": 1}).status_code == 403
    published = publisher.post(f"/pages/{page['id']}/publish")
    assert published.status_code == 200 and published.json()["status"] == "published"
    assert portal.public.get("/pagina-de-teste").status_code == 200
    assert publisher.post(f"/pages/{page['id']}/unpublish").json()["status"] == "draft"
    assert portal.public.get("/pagina-de-teste").status_code == 404
    assert publisher.get("/users").status_code == 403


def test_permissions_come_from_the_database_not_from_the_client(portal):
    editor = portal.login("editor")
    forged = {**editor.headers(), "X-Role": "administrador", "X-Permissions": "users.manage"}
    assert editor.client.get("/admin/api/users", headers=forged).status_code == 403
    assert editor.client.get("/admin/api/users?role=administrador", headers=forged).status_code == 403


def test_identity_lists_only_the_permissions_of_the_role(portal):
    for role in permissions.ROLES:
        session = portal.login(role)
        assert set(session.get("/auth/session").json()["permissions"]) == set(permissions.MATRIX[role])
