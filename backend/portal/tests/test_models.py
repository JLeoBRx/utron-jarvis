import sqlite3

from sqlalchemy import inspect, select, text

from safra_foundation import migrations
from safra_foundation.database import make_engine, sqlite_path
from safra_portal.domain import permissions
from safra_portal.domain.models import Base, Permission, Role, RolePermission
from safra_portal.infrastructure import MIGRATIONS
from safra_portal.infrastructure.db import make_session_factory

EXTRA_TABLES = {"safra_service", "alembic_version_portal"}


def _migrated(settings):
    engine = make_engine(settings.database_url)
    migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
    return engine


def test_migration_and_models_describe_the_same_schema(settings):
    engine = _migrated(settings)
    inspector = inspect(engine)
    in_database = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    in_models = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert set(in_database) - EXTRA_TABLES == set(in_models)
    for table, columns in in_models.items():
        assert in_database[table] == columns, table
    engine.dispose()


def test_database_is_owned_by_the_portal_and_goes_back_to_empty(settings):
    engine = _migrated(settings)
    assert migrations.database_owner(engine) == "portal"
    migrations.downgrade(engine, MIGRATIONS, "base", backups_dir=settings.backups_dir)
    assert set(inspect(engine).get_table_names()) == {"alembic_version_portal"}
    migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
    assert migrations.current_revision(engine, MIGRATIONS) == migrations.head_revision(MIGRATIONS)
    engine.dispose()


def test_seeded_roles_and_permissions_match_the_documented_matrix(settings):
    engine = _migrated(settings)
    with make_session_factory(engine)() as db:
        assert {r.key: r.name for r in db.scalars(select(Role))} == permissions.ROLES
        assert {p.key: p.description for p in db.scalars(select(Permission))} == permissions.PERMISSIONS
        stored: dict[str, set[str]] = {}
        for row in db.scalars(select(RolePermission)):
            stored.setdefault(row.role_key, set()).add(row.permission_key)
    assert stored == {role: set(keys) for role, keys in permissions.MATRIX.items()}
    engine.dispose()


def test_referential_integrity_is_enforced(settings):
    engine = _migrated(settings)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    path = sqlite_path(settings.database_url)
    engine.dispose()
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys=ON")
    try:
        for statement in (
            "INSERT INTO users (email, name, role_key) VALUES ('x@y.test', 'X', 'papel-inexistente')",
            "INSERT INTO content_versions (content_id, number, title, blocks) VALUES (9999, 1, 't', '[]')",
            "INSERT INTO contents (type, slug, title, blocks) VALUES ('outro', 's', 't', '[]')",
            "INSERT INTO releases (version, channel) VALUES ('1.0.0', 'canal-inexistente')",
        ):
            try:
                raw.execute(statement)
            except sqlite3.IntegrityError:
                continue
            raise AssertionError(f"o banco aceitou um dado inválido: {statement}")
    finally:
        raw.close()


def test_indexes_exist_for_the_frequent_lookups(settings):
    engine = _migrated(settings)
    inspector = inspect(engine)
    names = {index["name"] for table in inspector.get_table_names() for index in inspector.get_indexes(table)}
    for expected in ("ix_contents_type_status", "ix_content_versions_content_id", "ix_sessions_user_id",
                     "ix_sessions_expires_at", "ix_audit_events_at", "ix_publication_events_content_id", "ix_media_sha256"):
        assert expected in names, expected
    engine.dispose()
