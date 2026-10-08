"""Compatibilidade: o protetor de sessão do JARVIS foi removido.

Use este arquivo para garantir que a inicialização automática aponte para a HUD,
e não para uma tela de bloqueio.
"""
from __future__ import annotations
import os
import sys
import winreg
from pathlib import Path

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "JARVIS"
HERE = Path(__file__).resolve().parent


def command():
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = pyw if pyw.exists() else Path(sys.executable)
    return f'"{py}" "{HERE / "jarvis_hud.py"}" --boot'


def enable():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
    print("Inicialização automática do JARVIS ATIVADA (sem protetor).")
    print(command())


def disable():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
        print("Inicialização automática DESATIVADA.")
    except FileNotFoundError:
        print("Já estava desativada.")


def status():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            value = winreg.QueryValueEx(k, NAME)[0]
        print("ATIVADA:", value)
    except FileNotFoundError:
        print("DESATIVADA")


if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    {"on": enable, "off": disable, "status": status}.get(action, status)()
