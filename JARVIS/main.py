"""Ponto de entrada oficial do J.A.R.V.I.S.

Mantém compatibilidade com a arquitetura Fase 11 (core.runtime), mas também
funciona quando o projeto é distribuído sem a pasta core.
"""
try:
    from core.runtime import start_gui
except (ImportError, ModuleNotFoundError):
    from jarvis_hud import main as start_gui

if __name__ == "__main__":
    start_gui()
