"""Inicialização automática opcional com o Windows (HKCU\\...\\Run, sem administrador).

Uso:  python -m ultron.platform.autostart on | off | status | check
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


def points_here(value: str) -> bool:
    return str(paths.project_root() / "main.py").lower() in str(value or "").lower()


def is_enabled() -> bool:
    """Ativado = a entrada "JARVIS" (ou a antiga "ULTRON") aponta para ESTA instalação. Uma entrada "JARVIS"
    do JARVIS original (jarvis_hud.py) não conta."""
    if not supported():
        return False
    return points_here(_value(NAME)) or bool(legacy_entries())


def check() -> dict:
    """Diagnóstico da entrada de início automático (o original tinha `autostart.py check`). Só leitura."""
    if not supported():
        return {"status": "UNAVAILABLE", "text": "Início automático: disponível apenas no Windows."}
    value = _value(NAME)
    if not value and not legacy_entries():
        return {"status": "OFF", "text": "Início automático: DESATIVADO."}
    if points_here(value):
        if value.strip().lower() == command().lower():
            return {"status": "OK", "text": f"Início automático: ATIVADO para esta instalação ({value})."}
        return {"status": "STALE", "text": "Início automático: ATIVADO, mas com outro Python ou opções antigas. "
                                           f"Registrado: {value} | esperado: {command()}. Desative e ative de novo."}
    if legacy_entries():
        return {"status": "LEGACY", "text": "Início automático: entrada antiga 'ULTRON' desta instalação; ao ativar "
                                            "de novo ela vira 'JARVIS'."}
    if "jarvis_hud.py" in value.lower():
        return {"status": "ORIGINAL", "text": "A entrada 'JARVIS' aponta para o JARVIS original (jarvis_hud.py): "
                                              "esta instalação NÃO inicia com o Windows. Ao ativar aqui, a entrada "
                                              f"é substituída. Registrado: {value}"}
    return {"status": "OTHER", "text": f"A entrada 'JARVIS' aponta para outro programa: {value}"}


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
    elif action == "check":
        print(check()["text"])
    else:
        print("ATIVADA" if is_enabled() else "DESATIVADA", "|", command())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
