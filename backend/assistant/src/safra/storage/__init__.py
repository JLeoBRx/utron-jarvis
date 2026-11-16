"""Armazenamento do Assistant: o conjunto de migrações do banco privado e, nas próximas fases, os repositórios.

Camada 1. O motor, o backup e o executor de migrações vêm de `safra_foundation`.
"""
from pathlib import Path

from safra_foundation.migrations import MigrationSet

SERVICE = "assistant"
MIGRATIONS = MigrationSet(service=SERVICE, directory=Path(__file__).resolve().parent / "migrations")

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "implementado", "fase": 3, "resumo": "banco privado, migrações com backup, sessões de banco"}
