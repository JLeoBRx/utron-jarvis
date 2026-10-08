"""Compatibilidade: o antigo protetor de sessão foi desativado.

Se o Windows ainda possuir uma entrada de inicialização apontando para este
arquivo, ele simplesmente inicia o JARVIS normalmente, sem tela de PIN,
sem bloqueio e sem tela de proteção.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HUD = BASE_DIR / "jarvis_hud.py"


def main() -> int:
    if not HUD.exists():
        print(f"JARVIS HUD não encontrada: {HUD}")
        return 1
    try:
        return subprocess.call([sys.executable, str(HUD), "--boot"], cwd=str(BASE_DIR))
    except Exception as exc:
        print(f"Falha ao iniciar JARVIS: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
