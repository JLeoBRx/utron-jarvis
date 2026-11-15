"""Apoio aos testes: cada teste recebe uma pasta de dados temporária. Nenhum dado real é tocado."""
from __future__ import annotations

from pathlib import Path

import pytest

from safra.core.config import Settings, load_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(env={}, environment="test", data_dir=tmp_path / "dados", log_to_file=False)
