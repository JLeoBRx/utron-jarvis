"""Inicialização automática opcional com o Windows (HKCU\\...\\Run, sem administrador).

Uso:  python -m ultron.platform.autostart on | off | status
"""
from __future__ import annotations

import os
import sys

from ..config import paths

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "ULTRON"


def command() -> str:
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.exists(pyw):
        py = pyw                          # sem janela de console
    main = paths.project_root() / "main.py"
    return f'"{py}" "{main}" --boot'


def supported() -> bool:
    return sys.platform == "win32"


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return bool(winreg.QueryValueEx(key, NAME)[0])
    except FileNotFoundError:
        return False


def enable() -> str:
    if not supported():
        raise OSError("inicialização automática disponível apenas no Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
    return command()


def disable() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, NAME)
        return True
    except FileNotFoundError:
        return False


def main(argv: list[str]) -> int:
    action = argv[1].lower() if len(argv) > 1 else "status"
    if action == "on":
        print("Inicialização automática ATIVADA:", enable())
    elif action == "off":
        print("Inicialização automática DESATIVADA." if disable() else "Já estava desativada.")
    else:
        print("ATIVADA" if is_enabled() else "DESATIVADA", "|", command())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
