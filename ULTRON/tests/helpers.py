"""Utilitários dos testes: diretórios temporários isolados e fábricas de componentes.

Os testes nunca tocam os dados reais do usuário: ``ULTRON_DATA_DIR`` e ``HOME`` apontam
para pastas temporárias criadas antes de qualquer import do pacote.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

_SESSION_DIR = Path(tempfile.mkdtemp(prefix="ultron-tests-"))
os.environ.setdefault("ULTRON_DATA_DIR", str(_SESSION_DIR / "data"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QUICK = os.environ.get("ULTRON_TEST_QUICK") == "1"           # TEST_ULTRON.py --quick


def temp_dir(prefix: str = "case-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix, dir=_SESSION_DIR))


def cleanup() -> None:
    shutil.rmtree(_SESSION_DIR, ignore_errors=True)


def module_available(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def qt_available() -> bool:
    if not module_available("PySide6"):
        return False
    import importlib
    try:
        importlib.import_module("PySide6.QtWidgets")
        return True
    except ImportError:                  # biblioteca do sistema ausente (ex.: libEGL em servidores)
        return False


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_bus_state():
    from ultron.core.event_bus import EventBus
    from ultron.core.state import StateStore
    bus = EventBus()
    state = StateStore(bus)
    state.set_runtime_state("IDLE")
    return bus, state


def make_memory(bus=None, state=None, *, path: Path | None = None):
    from ultron.memory.store import Database
    from ultron.memory.system import MemorySystem
    db = Database(path or temp_dir("mem-") / "ultron.sqlite3")
    return MemorySystem(db, bus=bus, state=state, import_legacy=False)


def make_settings(**values):
    from ultron.config.settings import Settings
    settings = Settings()
    settings.apply(values, source="teste")
    return settings
