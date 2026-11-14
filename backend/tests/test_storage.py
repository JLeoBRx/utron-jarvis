import sqlite3

import pytest
from sqlalchemy import inspect, text

from safra.core.errors import StorageError
from safra.storage import backup, migrations
from safra.storage.database import make_engine, ping, sqlite_path


@pytest.fixture
def engine(settings):
    engine = make_engine(settings.database_url)
    yield engine
    engine.dispose()


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


def test_fresh_database_is_migrated_to_head_without_backup(engine, settings):
    assert migrations.current_revision(engine) is None
    result = migrations.upgrade(engine, backups_dir=settings.backups_dir)
    assert result.changed and result.after == migrations.head_revision() == "0001"
    assert result.backup is None                              # banco vazio: nada a proteger
    assert "app_meta" in inspect(engine).get_table_names()


def test_upgrade_is_idempotent(engine, settings):
    migrations.upgrade(engine, backups_dir=settings.backups_dir)
    again = migrations.upgrade(engine, backups_dir=settings.backups_dir)
    assert not again.changed and again.backup is None
    assert backup.list_backups(settings.backups_dir) == []


def test_downgrade_and_upgrade_back_up_existing_data_first(engine, settings):
    migrations.upgrade(engine, backups_dir=settings.backups_dir)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO app_meta (key, value) VALUES ('instalacao', 'abc')"))
    down = migrations.downgrade(engine, "base", backups_dir=settings.backups_dir)
    assert down.after is None and down.backup is not None
    assert "app_meta" not in inspect(engine).get_table_names()
    # o backup guarda o dado que a migração desfeita apagou
    with sqlite3.connect(down.backup.path) as copy:
        assert copy.execute("SELECT value FROM app_meta WHERE key='instalacao'").fetchone() == ("abc",)
    up = migrations.upgrade(engine, backups_dir=settings.backups_dir)
    assert up.after == "0001" and up.backup is not None
    assert len(backup.list_backups(settings.backups_dir)) == 2


def test_backup_is_verified_single_file_and_never_overwrites(engine, settings):
    migrations.upgrade(engine, backups_dir=settings.backups_dir)
    source = sqlite_path(settings.database_url)
    first = backup.backup_sqlite(source, settings.backups_dir, reason="Teste Manual!")
    second = backup.backup_sqlite(source, settings.backups_dir, reason="Teste Manual!")
    assert first.path != second.path and first.path.exists() and second.path.exists()
    assert "teste-manual" in first.path.name
    assert backup.verify_sqlite(first.path)
    leftovers = [p.name for p in settings.backups_dir.iterdir() if p.name.endswith(("-wal", "-shm"))]
    assert leftovers == []


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
