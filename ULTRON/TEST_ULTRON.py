"""Compatibilidade: o executor de testes agora é ``TEST_JARVIS.py`` (mesmos argumentos)."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("TEST_JARVIS.py")), run_name="__main__")
