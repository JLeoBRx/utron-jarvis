"""JARVIS — ponto de entrada.

    python main.py              HUB principal (JARVIS CORE; TARDIS sob demanda)
    python main.py --headless   console de texto
    python main.py --diagnose   saúde completa + voz (8 etapas)
    python main.py --help       todos os comandos (voz, backup, exportação, --status/--stop)

O pacote interno continua se chamando ``ultron`` para preservar dados e configurações.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ultron.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
