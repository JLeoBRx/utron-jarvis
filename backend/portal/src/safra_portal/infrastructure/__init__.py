"""Infraestrutura do Portal: banco, migrações, conteúdo inicial e limite de frequência."""
from pathlib import Path

from safra_foundation.migrations import MigrationSet

SERVICE = "portal"
MIGRATIONS = MigrationSet(service=SERVICE, directory=Path(__file__).resolve().parent / "migrations")
