from __future__ import annotations
import importlib
import threading

from .brain import JarvisBrain

_brain = JarvisBrain()
_hud_thread = None


def brain() -> JarvisBrain:
    return _brain


def start_gui() -> int:
    """Inicializa a aplicação visual atual sem duplicar o núcleo antigo."""
    _brain.start()
    hud = importlib.import_module("jarvis_hud")
    return hud.main()


def status():
    return _brain.snapshot()
