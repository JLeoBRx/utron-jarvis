import sqlite3

import pytest
from sqlalchemy import inspect, text

from safra_foundation import backup, migrations
from safra_foundation.database import make_engine, ping, sqlite_path
from safra_foundation.errors import StorageError
from safra_foundation.migrations import MigrationSet


def test_sqlite_connections_use_wal_and_foreign_keys(engine):
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert ping(engine)


def test_sqlite_path_only_for_files():
    assert sqlite_path("sqlite:///:memory:") is None
    assert sqlite_path("postgresql://u:p@host/db") is None
    assert sqlite_path("sqlite:////tmp/x.sqlite3").name == "x.sqlite3"


def test_invalid_database_url_is_a_storage_error():
    with pytest.raises(StorageError):
        make_engine("isto não é uma url")


def test_fresh_database_is_migrated_to_head_without_backup(engine, migrations_set, backups_dir):
    assert migrations.current_revision(engine, migrations_set) is None
    assert migrations.database_owner(engine) is None
    result = migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    assert result.changed and result.after == migrations.head_revision(migrations_set) == "0001"
    assert result.backup is None                              # banco vazio: nada a proteger
    tables = inspect(engine).get_table_names()
    assert "app_meta" in tables and "alembic_version_teste" in tables
    assert migrations.database_owner(engine) == "teste"


def test_upgrade_is_idempotent(engine, migrations_set, backups_dir):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    again = migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    assert not again.changed and again.backup is None
    assert backup.list_backups(backups_dir, prefix="safra-teste") == []


def test_downgrade_and_upgrade_back_up_existing_data_first(engine, migrations_set, backups_dir):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO app_meta (key, value) VALUES ('instalacao', 'abc')"))
    down = migrations.downgrade(engine, migrations_set, "base", backups_dir=backups_dir)
    assert down.after is None and down.backup is not None
    assert "app_meta" not in inspect(engine).get_table_names()
    with sqlite3.connect(down.backup.path) as copy:           # o backup guarda o dado que a migração desfeita apagou
        assert copy.execute("SELECT value FROM app_meta WHERE key='instalacao'").fetchone() == ("abc",)
    up = migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    assert up.after == "0001" and up.backup is not None
    assert len(backup.list_backups(backups_dir, prefix="safra-teste")) == 2


def test_a_database_owned_by_another_service_is_refused(engine, migrations_set, backups_dir):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    other = MigrationSet(service="outro", directory=migrations_set.directory)
    with pytest.raises(StorageError) as info:
        migrations.upgrade(engine, other, backups_dir=backups_dir)
    assert "não compartilham banco" in info.value.message
    with pytest.raises(StorageError):
        migrations.ensure_owner(engine, other)
    assert "alembic_version_outro" not in inspect(engine).get_table_names()      # nada foi criado


def test_a_database_with_foreign_tables_and_no_owner_is_refused(engine, migrations_set):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE coisa_alheia (id INTEGER PRIMARY KEY)"))
    with pytest.raises(StorageError):
        migrations.upgrade(engine, migrations_set)


def test_backup_is_verified_single_file_and_never_overwrites(engine, migrations_set, backups_dir, db_url):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    source = sqlite_path(db_url)
    first = backup.backup_sqlite(source, backups_dir, reason="Teste Manual!")
    second = backup.backup_sqlite(source, backups_dir, reason="Teste Manual!")
    assert first.path != second.path and first.path.exists() and second.path.exists()
    assert "teste-manual" in first.path.name
    assert backup.verify_sqlite(first.path)
    assert [p.name for p in backups_dir.iterdir() if p.name.endswith(("-wal", "-shm"))] == []


def test_restore_brings_the_data_back_and_keeps_the_replaced_database(engine, migrations_set, backups_dir, db_url):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO app_meta (key, value) VALUES ('nota', 'original')"))
    source = sqlite_path(db_url)
    saved = backup.backup_sqlite(source, backups_dir, reason="antes do desastre")
    with engine.begin() as connection:                         # o "desastre": dado alterado e dado novo
        connection.execute(text("UPDATE app_meta SET value='estragado' WHERE key='nota'"))
        connection.execute(text("INSERT INTO app_meta (key, value) VALUES ('lixo', 'x')"))
    engine.dispose()                                           # restauração é feita com o serviço parado
    safety = backup.restore_sqlite(saved.path, source, safety_dir=backups_dir)
    restored = make_engine(db_url)
    try:
        with restored.connect() as connection:
            rows = dict(connection.execute(text("SELECT key, value FROM app_meta")).all())
        assert rows == {"nota": "original"}
        assert migrations.current_revision(restored, migrations_set) == "0001"
    finally:
        restored.dispose()
    assert safety is not None                                  # o banco substituído não foi perdido
    with sqlite3.connect(safety.path) as replaced:
        assert replaced.execute("SELECT value FROM app_meta WHERE key='nota'").fetchone() == ("estragado",)


def test_restore_refuses_a_corrupt_backup_and_changes_nothing(engine, migrations_set, backups_dir, db_url, tmp_path):
    migrations.upgrade(engine, migrations_set, backups_dir=backups_dir)
    engine.dispose()
    source = sqlite_path(db_url)
    before = source.read_bytes()
    corrupt = tmp_path / "corrompido.sqlite3"
    corrupt.write_bytes(b"isto nao e um banco" * 100)
    with pytest.raises(StorageError):
        backup.restore_sqlite(corrupt, source, safety_dir=backups_dir)
    assert source.read_bytes() == before


def test_verify_rejects_missing_empty_and_corrupt_files(tmp_path):
    assert not backup.verify_sqlite(tmp_path / "nao-existe.sqlite3")
    empty = tmp_path / "vazio.sqlite3"
    empty.write_bytes(b"")
    assert not backup.verify_sqlite(empty)
    corrupt = tmp_path / "corrompido.sqlite3"
    corrupt.write_bytes(b"isto nao e um banco" * 100)
    assert not backup.verify_sqlite(corrupt)


def test_backup_of_missing_database_is_a_storage_error(tmp_path):
    with pytest.raises(StorageError):
        backup.backup_sqlite(tmp_path / "nada.sqlite3", tmp_path / "backups")
