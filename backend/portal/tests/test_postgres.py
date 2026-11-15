"""Banco de produção (AD-04): as migrações e o fluxo principal do CMS rodam sobre PostgreSQL.

Só executa quando ``SAFRA_PORTAL_TEST_POSTGRES_URL`` aponta para um banco de teste descartável (no CI, um contêiner).
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from safra_foundation import migrations
from safra_foundation.database import make_engine
from safra_portal.api.app import create_app
from safra_portal.config import load_settings
from safra_portal.domain.models import Base
from safra_portal.infrastructure import MIGRATIONS
from safra_portal.infrastructure.db import transaction

from conftest import PASSWORD, page_data

URL = os.environ.get("SAFRA_PORTAL_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="sem PostgreSQL de teste (defina SAFRA_PORTAL_TEST_POSTGRES_URL)")


@pytest.fixture
def clean_database():
    engine = make_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def test_migrations_apply_and_revert_on_postgresql(clean_database):
    engine = clean_database
    result = migrations.upgrade(engine, MIGRATIONS)
    assert result.after == migrations.head_revision(MIGRATIONS) and migrations.database_owner(engine) == "portal"
    inspector = inspect(engine)
    in_database = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    for table in Base.metadata.sorted_tables:
        assert in_database[table.name] == {c.name for c in table.columns}, table.name
    assert any(fk["referred_table"] == "content_versions" for fk in inspector.get_foreign_keys("contents"))
    migrations.downgrade(engine, MIGRATIONS, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version_portal"}


def test_cms_flow_on_postgresql(clean_database, tmp_path):
    settings = load_settings(env={}, environment="test", data_dir=tmp_path / "portal", log_to_file=False, database_url=URL)
    app = create_app(settings)
    origin = settings.public_base_url
    with TestClient(app, base_url=origin) as client:
        assert client.get("/").status_code == 200 and client.get("/sobre").status_code == 200       # conteúdo inicial
        with transaction(app.state.session_factory) as db:
            app.state.auth.create_user(db, email="dono@exemplo.test", name="Dono", role="administrador", password=PASSWORD)
        login = client.post("/admin/api/auth/login", json={"email": "dono@exemplo.test", "password": PASSWORD},
                            headers={"Origin": origin})
        assert login.status_code == 200
        headers = {"Origin": origin, "X-CSRF-Token": login.json()["csrf_token"]}
        page = client.post("/admin/api/pages", json=page_data(title="No PostgreSQL"), headers=headers)
        assert page.status_code == 201, page.text
        page_id = page.json()["id"]
        assert client.get("/pagina-de-teste").status_code == 404
        assert client.post(f"/admin/api/pages/{page_id}/publish", headers=headers).status_code == 200
        assert "No PostgreSQL" in client.get("/pagina-de-teste").text
        saved = client.put(f"/admin/api/pages/{page_id}", json={**page_data(title="Segunda versão"), "lock_version": 1},
                           headers=headers)
        assert saved.status_code == 200 and saved.json()["has_unpublished_changes"] is True
        versions = client.get(f"/admin/api/pages/{page_id}/versions").json()
        assert [v["number"] for v in versions] == [2, 1]
        assert client.post(f"/admin/api/pages/{page_id}/versions/{versions[-1]['id']}/restore", headers=headers).status_code == 200
        assert client.get("/admin/api/dashboard").json()["pages"]["published"] >= 12
        assert client.get("/admin/api/audit").json()[0]["action"] == "page.restore"
