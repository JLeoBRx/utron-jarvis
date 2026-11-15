from datetime import timedelta

import pytest
from sqlalchemy import select, update

from safra_foundation import passwords
from safra_portal.auth.deps import SESSION_COOKIE
from safra_portal.domain.models import AuditEvent, Session, User, utcnow
from safra_portal.infrastructure.db import transaction

from conftest import PASSWORD, Portal


def _login(portal: Portal, email: str, password: str, client=None, origin: str | None = None):
    client = client or portal.client()
    headers = {} if origin == "" else {"Origin": origin or portal.origin}
    return client, client.post("/admin/api/auth/login", json={"email": email, "password": password}, headers=headers)


def test_a_fresh_portal_has_no_account_at_all(portal):
    with transaction(portal.app.state.session_factory) as db:
        assert db.scalar(select(User)) is None
    for email, password in (("admin@exemplo.test", "admin"), ("admin", "admin"), ("admin@admin.com", "password"),
                            ("root@localhost", "")):
        _, response = _login(portal, email, password)
        assert response.status_code == 401, (email, response.text)


def test_login_sets_a_strict_http_only_cookie_scoped_to_the_admin(portal):
    portal.create_user("administrador")
    client, response = _login(portal, "administrador@exemplo.test", PASSWORD)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert SESSION_COOKIE in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/admin" in cookie
    body = response.json()
    assert body["user"]["role"] == "administrador" and "users.manage" in body["permissions"] and body["csrf_token"]
    assert PASSWORD not in response.text
    assert client.get("/admin/api/auth/session").status_code == 200


def test_cookie_is_secure_when_the_site_is_https(tmp_path):
    from safra_portal.config import load_settings
    settings = load_settings(env={}, environment="test", data_dir=tmp_path / "p", log_to_file=False,
                             public_base_url="https://safra.example")
    portal = Portal(settings)
    try:
        portal.create_user("administrador")
        _, response = _login(portal, "administrador@exemplo.test", PASSWORD)
        assert response.status_code == 200 and "secure" in response.headers["set-cookie"].lower()
        assert "max-age=31536000" in response.headers["strict-transport-security"]
    finally:
        portal.close()


def test_wrong_password_unknown_user_and_inactive_user_look_the_same(portal):
    portal.create_user("editor")
    inactive = portal.create_user("editor", "inativo@exemplo.test")
    with transaction(portal.app.state.session_factory) as db:
        db.get(User, inactive).is_active = False
    answers = [_login(portal, "editor@exemplo.test", "senha errada 123456")[1],
               _login(portal, "ninguem@exemplo.test", PASSWORD)[1],
               _login(portal, "inativo@exemplo.test", PASSWORD)[1]]
    assert {r.status_code for r in answers} == {401}
    assert len({r.json()["error"]["message"] for r in answers}) == 1
    assert len({r.json()["error"]["code"] for r in answers}) == 1


def test_account_locks_after_repeated_failures_even_with_the_right_password(portal):
    portal.create_user("editor")
    for _ in range(portal.settings.lockout_threshold):
        assert _login(portal, "editor@exemplo.test", "senha errada 123456")[1].status_code == 401
    assert _login(portal, "editor@exemplo.test", PASSWORD)[1].status_code == 401       # bloqueada
    with transaction(portal.app.state.session_factory) as db:
        user = db.scalar(select(User).where(User.email == "editor@exemplo.test"))
        assert user.locked_until is not None
        user.locked_until = utcnow() - timedelta(seconds=1)                             # o prazo passa
    assert _login(portal, "editor@exemplo.test", PASSWORD)[1].status_code == 200
    with transaction(portal.app.state.session_factory) as db:
        actions = set(db.scalars(select(AuditEvent.action)))
    assert {"login.failed", "login.locked", "login.ok"} <= actions


def test_login_is_rate_limited_per_address(portal):
    statuses = [_login(portal, f"x{i}@exemplo.test", "qualquer senha 1234")[1].status_code
                for i in range(portal.settings.login_attempts_per_ip + 2)]
    assert statuses[: portal.settings.login_attempts_per_ip] == [401] * portal.settings.login_attempts_per_ip
    assert statuses[-1] == 429


def test_login_from_another_origin_is_refused(portal):
    portal.create_user("editor")
    assert _login(portal, "editor@exemplo.test", PASSWORD, origin="https://evil.example")[1].status_code == 403
    assert _login(portal, "editor@exemplo.test", PASSWORD, origin="")[1].status_code == 403      # sem Origin


def test_changes_need_origin_and_the_csrf_token_of_the_session(portal):
    admin = portal.login("administrador")
    body = {"slug": "x", "name": "X"}
    assert admin.client.post("/admin/api/categories", json=body, headers={"Origin": portal.origin}).status_code == 403
    assert admin.client.post("/admin/api/categories", json=body,
                             headers={"Origin": portal.origin, "X-CSRF-Token": "errado"}).status_code == 403
    assert admin.client.post("/admin/api/categories", json=body,
                             headers={"Origin": "https://evil.example", "X-CSRF-Token": admin.csrf}).status_code == 403
    assert admin.client.post("/admin/api/categories", json=body, headers={"X-CSRF-Token": admin.csrf}).status_code == 403
    other = portal.login("editor")                                  # o código de outra sessão não serve
    assert admin.client.post("/admin/api/categories", json=body,
                             headers={"Origin": portal.origin, "X-CSRF-Token": other.csrf}).status_code == 403
    assert admin.post("/categories", json=body).status_code == 201


def test_session_expires_by_inactivity_and_by_absolute_time(portal):
    admin = portal.login("administrador")
    assert admin.get("/auth/session").status_code == 200
    with transaction(portal.app.state.session_factory) as db:
        db.execute(update(Session).values(last_seen_at=utcnow() - timedelta(minutes=portal.settings.session_idle_minutes + 1)))
    assert admin.get("/auth/session").status_code == 401            # inatividade
    again = portal.login("administrador", create=False)
    with transaction(portal.app.state.session_factory) as db:
        db.execute(update(Session).where(Session.revoked_at.is_(None)).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert again.get("/auth/session").status_code == 401            # prazo absoluto, mesmo em uso
    with transaction(portal.app.state.session_factory) as db:
        assert all(s.revoked_at is not None for s in db.scalars(select(Session)))


def test_logout_revokes_the_session_on_the_server(portal):
    admin = portal.login("administrador")
    token = admin.client.cookies.get(SESSION_COOKIE)
    assert admin.post("/auth/logout").status_code == 200
    replay = portal.client()
    replay.cookies.set(SESSION_COOKIE, token, path="/admin")
    assert replay.get("/admin/api/auth/session").status_code == 401   # o cookie antigo não vale mais


def test_a_forged_or_garbage_cookie_is_not_a_session(portal):
    portal.create_user("administrador")
    for value in ("", "x", "a" * 43, "a" * 5000, "../../etc/passwd", "' OR 1=1 --"):
        client = portal.client()
        client.cookies.set(SESSION_COOKIE, value, path="/admin")
        assert client.get("/admin/api/auth/session").status_code == 401


def test_only_token_digests_are_stored(portal):
    admin = portal.login("administrador")
    token = admin.client.cookies.get(SESSION_COOKIE)
    with transaction(portal.app.state.session_factory) as db:
        session = db.scalar(select(Session))
        user = db.scalar(select(User))
    assert token not in (session.token_digest, session.csrf_token) and len(session.token_digest) == 64
    assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash


def test_role_change_and_deactivation_take_effect_on_the_next_request(portal):
    admin = portal.login("administrador")
    editor = portal.login("editor")
    assert editor.post("/pages", json={"slug": "a", "title": "A"}).status_code == 201
    editor_id = editor.session["user"]["id"]
    assert admin.patch(f"/users/{editor_id}", json={"role": "publicador"}).status_code == 200
    assert editor.post("/pages", json={"slug": "b", "title": "B"}).status_code == 403
    assert admin.patch(f"/users/{editor_id}", json={"is_active": False}).status_code == 200
    assert editor.get("/auth/session").status_code == 401


def test_the_last_active_administrator_cannot_be_demoted_or_deactivated(portal):
    admin = portal.login("administrador")
    me = admin.session["user"]["id"]
    assert admin.patch(f"/users/{me}", json={"role": "editor"}).status_code == 409
    assert admin.patch(f"/users/{me}", json={"is_active": False}).status_code == 409
    portal.create_user("administrador", "outro@exemplo.test")
    assert admin.patch(f"/users/{me}", json={"role": "editor"}).status_code == 200


def test_new_account_has_no_password_and_is_claimed_by_a_single_use_token(portal):
    admin = portal.login("administrador")
    created = admin.post("/users", json={"email": "Nova.Pessoa@Exemplo.test", "name": "Nova Pessoa", "role": "editor"})
    assert created.status_code == 201 and created.json()["user"]["has_password"] is False
    assert created.json()["user"]["email"] == "nova.pessoa@exemplo.test"
    token = created.json()["recovery_token"]
    assert _login(portal, "nova.pessoa@exemplo.test", "")[1].status_code == 401          # sem senha não entra
    client = portal.client()
    headers = {"Origin": portal.origin}
    weak = client.post("/admin/api/auth/recover", json={"token": token, "new_password": "curta"}, headers=headers)
    assert weak.status_code == 422
    ok = client.post("/admin/api/auth/recover", json={"token": token, "new_password": "uma senha nova e longa"}, headers=headers)
    assert ok.status_code == 200
    again = client.post("/admin/api/auth/recover", json={"token": token, "new_password": "outra senha nova longa"}, headers=headers)
    assert again.status_code == 401                                                      # uso único
    assert _login(portal, "nova.pessoa@exemplo.test", "uma senha nova e longa")[1].status_code == 200


def test_recovery_revokes_sessions_and_expired_or_replaced_tokens_fail(portal):
    admin = portal.login("administrador")
    editor = portal.login("editor")
    editor_id = editor.session["user"]["id"]
    first = admin.post(f"/users/{editor_id}/recovery-token").json()["recovery_token"]
    second = admin.post(f"/users/{editor_id}/recovery-token").json()["recovery_token"]
    client, headers = portal.client(), {"Origin": portal.origin}
    assert client.post("/admin/api/auth/recover", json={"token": first, "new_password": "senha nova bem longa 1"},
                       headers=headers).status_code == 401                               # substituído pelo segundo
    assert client.post("/admin/api/auth/recover", json={"token": second, "new_password": "senha nova bem longa 2"},
                       headers=headers).status_code == 200
    assert editor.get("/auth/session").status_code == 401                                # sessões antigas encerradas
    third = admin.post(f"/users/{editor_id}/recovery-token").json()["recovery_token"]
    from safra_portal.domain.models import RecoveryToken
    with transaction(portal.app.state.session_factory) as db:
        db.execute(update(RecoveryToken).where(RecoveryToken.used_at.is_(None)).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.post("/admin/api/auth/recover", json={"token": third, "new_password": "senha nova bem longa 3"},
                       headers=headers).status_code == 401                               # vencido


def test_changing_the_password_requires_the_current_one_and_ends_other_sessions(portal):
    first = portal.login("editor")
    second = portal.login("editor", create=False)
    assert first.post("/auth/password", json={"current": "errada 1234567", "new": "senha nova bem comprida"}).status_code == 401
    assert first.post("/auth/password", json={"current": PASSWORD, "new": "senha nova bem comprida"}).status_code == 200
    assert first.get("/auth/session").status_code == 200 and second.get("/auth/session").status_code == 401
    assert _login(portal, "editor@exemplo.test", PASSWORD)[1].status_code == 401
    assert _login(portal, "editor@exemplo.test", "senha nova bem comprida")[1].status_code == 200


def test_production_password_cost_is_the_documented_one(settings):
    from safra_portal.auth.service import AuthService
    production_like = settings.model_copy(update={"environment": "development"})
    assert AuthService(production_like).params == passwords.DEFAULT_PARAMS
    assert (passwords.DEFAULT_PARAMS.n, passwords.DEFAULT_PARAMS.r, passwords.DEFAULT_PARAMS.p) == (2 ** 17, 8, 1)


def test_sessions_can_be_listed_and_revoked_only_by_their_owner(portal):
    admin = portal.login("administrador")
    editor = portal.login("editor")
    mine = admin.get("/sessions").json()
    assert len(mine) == 1 and mine[0]["current"] is True
    theirs = editor.get("/sessions").json()[0]["id"]
    assert admin.delete(f"/sessions/{theirs}").status_code == 404
    assert editor.delete(f"/sessions/{theirs}").status_code == 200
    assert editor.get("/auth/session").status_code == 401


@pytest.mark.parametrize("email", ["", "sem-arroba", "a@b", "a b@c.test", "x" * 300 + "@c.test"])
def test_invalid_emails_are_rejected_when_creating_accounts(portal, email):
    admin = portal.login("administrador")
    assert admin.post("/users", json={"email": email, "name": "X", "role": "editor"}).status_code == 422
