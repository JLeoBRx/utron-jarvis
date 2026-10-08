"""ULTRON — ponto de entrada.

    python main.py              HUB neural
    python main.py --headless   console de texto
    python main.py --diagnose   relatório de saúde
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ultron.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
