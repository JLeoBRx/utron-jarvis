"""Mensagens para quem iniciou o SAFRA sem console (``pythonw``, atalho, ``START_JARVIS.bat``).

Sem console, ``print`` não aparece em lugar nenhum: um erro de inicialização faria o SAFRA simplesmente sumir.
No Windows usa a caixa de mensagem do próprio sistema (``MessageBoxW``), que funciona mesmo quando a falha foi
do Qt; fora do Windows tenta o Qt. Sem nenhum dos dois, devolve ``None`` — o registro (log) continua valendo.
"""
from __future__ import annotations

import sys

MB_OK, MB_YESNO = 0x0, 0x4
MB_ICONERROR, MB_ICONWARNING, MB_ICONINFORMATION = 0x10, 0x30, 0x40
MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
IDYES = 6


def has_console() -> bool:
    """Há alguém lendo a saída e podendo responder no terminal?"""
    try:
        return (sys.stdout is not None and sys.stdin is not None and sys.stdin.isatty()
                and sys.stdout.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def show(title: str, text: str, *, ask: bool = False, kind: str = "error") -> bool | None:
    """Mostra ``text``. ``ask=True``: botões Sim/Não e devolve True/False. ``None`` = não foi possível mostrar."""
    if sys.platform == "win32":
        try:
            import ctypes
            icon = {"error": MB_ICONERROR, "warning": MB_ICONWARNING}.get(kind, MB_ICONINFORMATION)
            flags = (MB_YESNO if ask else MB_OK) | icon | MB_SETFOREGROUND | MB_TOPMOST
            answer = ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            return answer == IDYES if ask else True
        except Exception:
            pass
    try:
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        box = QtWidgets.QMessageBox
        if ask:
            answer = box.question(None, title, text, box.Yes | box.No, box.Yes)
            return answer == box.Yes
        (box.critical if kind == "error" else box.information)(None, title, text)
        del app
        return True
    except Exception:
        return None
