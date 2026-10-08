"""Resolução de caminhos do ULTRON.

* ``project_root()``: pasta do produto (onde ficam ``assets/``, ``plugins/`` e os .bat).
* ``data_dir()``: dados do usuário (banco, grafo, world model, logs). No Windows fica em
  ``%LOCALAPPDATA%\\ULTRON``; em outros sistemas em ``$XDG_DATA_HOME/ultron``.
  A variável ``ULTRON_DATA_DIR`` sobrescreve (usada pelos testes).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    override = os.environ.get("ULTRON_HOME")
    if override:
        return Path(override)
    return _PACKAGE_DIR.parent


def assets_dir() -> Path:
    return project_root() / "assets"


def plugins_dir() -> Path:
    return project_root() / "plugins"


def data_dir() -> Path:
    override = os.environ.get("ULTRON_DATA_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "ULTRON"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "ultron"
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file(*parts: str) -> Path:
    path = data_dir().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_file("ultron.sqlite3")


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_jarvis_database() -> Path | None:
    """Banco do JARVIS legado (fatos, preferências e automações), se existir."""
    candidates = []
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        candidates.append(Path(base) / "JARVIS" / "assistant.sqlite3")
    else:
        candidates.append(Path.home() / "AppData" / "Local" / "JARVIS" / "assistant.sqlite3")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def stt_models_dir() -> Path:
    return assets_dir() / "stt"


def voices_dir() -> Path:
    return assets_dir() / "voices"


def images_dir() -> Path:
    path = data_dir() / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path
