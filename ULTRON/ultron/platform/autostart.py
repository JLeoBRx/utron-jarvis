"""Inicialização automática opcional com o Windows (HKCU\\...\\Run, sem administrador).

Uso:  python -m ultron.platform.autostart on | off | status
"""
from __future__ import annotations

import os
import sys

from ..config import paths

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "JARVIS"
LEGACY_NAMES = ("ULTRON",)        # entrada criada pela identidade anterior (mesmo programa)


def command() -> str:
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.exists(pyw):
        py = pyw                          # sem janela de console
    main = paths.project_root() / "main.py"
    return f'"{py}" "{main}" --boot'


def supported() -> bool:
    return sys.platform == "win32"


def _value(name: str) -> str:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return str(winreg.QueryValueEx(key, name)[0] or "")
    except FileNotFoundError:
        return ""


def legacy_entries() -> list[str]:
    """Entradas antigas (ULTRON) que apontam para este mesmo programa."""
    if not supported():
        return []
    main = str(paths.project_root() / "main.py").lower()
    return [name for name in LEGACY_NAMES if main in _value(name).lower()]


def is_enabled() -> bool:
    if not supported():
        return False
    return bool(_value(NAME)) or bool(legacy_entries())


def enable() -> str:
    """Pedido explícito do usuário: grava a entrada JARVIS e remove a entrada antiga do mesmo programa
    (evita duas inicializações)."""
    if not supported():
        raise OSError("inicialização automática disponível apenas no Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        for legacy in legacy_entries():
            try:
                winreg.DeleteValue(key, legacy)
            except FileNotFoundError:
                pass
    return command()


def disable() -> bool:
    if not supported():
        return False
    import winreg
    removed = False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name in (NAME, *legacy_entries()):
            try:
                winreg.DeleteValue(key, name)
                removed = True
            except FileNotFoundError:
                pass
    return removed


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
