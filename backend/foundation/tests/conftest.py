from pathlib import Path

import pytest

from safra_foundation.database import make_engine
from safra_foundation.migrations import MigrationSet

MIGRATIONS = MigrationSet(service="teste", directory=Path(__file__).resolve().parent / "fixture_migrations")


@pytest.fixture
def migrations_set() -> MigrationSet:
    return MIGRATIONS


@pytest.fixture
def db_url(tmp_path) -> str:
    return "sqlite:///" + (tmp_path / "dados" / "teste.sqlite3").as_posix()


@pytest.fixture
def backups_dir(tmp_path) -> Path:
    return tmp_path / "dados" / "backups"


@pytest.fixture
def engine(db_url):
    engine = make_engine(db_url)
    yield engine
    engine.dispose()
