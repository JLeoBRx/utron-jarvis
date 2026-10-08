"""Memória de preferências do usuário (lista permitida, sem credenciais)."""
from __future__ import annotations

import time

from .store import Database, clean_text

ALLOWED = {
    "profile_name": "Nome do usuário",
    "address_me_as": "Forma de tratamento",
    "city": "Cidade",
    "language": "Idioma",
    "preferred_editor": "Editor preferido",
    "preferred_browser": "Navegador preferido",
    "projects_root": "Pasta de projetos",
    "verbosity": "Nível de detalhe das respostas",
}


class PreferenceMemory:
    def __init__(self, db: Database):
        self.db = db

    def set(self, name: str, value: str) -> str:
        if name not in ALLOWED:
            raise ValueError(f"preferência fora da lista permitida: {name}")
        value = clean_text(value, 200, field="valor")
        self.db.execute("INSERT INTO preferences(name,value,updated_at) VALUES(?,?,?) "
                        "ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                        (name, value, time.time()))
        return value

    def get(self, name: str, default: str | None = None) -> str | None:
        row = self.db.one("SELECT value FROM preferences WHERE name=?", (name,))
        return str(row["value"]) if row else default

    def all(self) -> dict[str, str]:
        return {r["name"]: r["value"] for r in self.db.query("SELECT name,value FROM preferences ORDER BY name")}

    def delete(self, name: str) -> bool:
        return self.db.execute("DELETE FROM preferences WHERE name=?", (name,)).rowcount > 0

    def prompt_context(self) -> str:
        prefs = self.all()
        parts = []
        if prefs.get("profile_name"):
            parts.append(f"O usuário se chama {prefs['profile_name']}.")
        if prefs.get("address_me_as"):
            parts.append(f"Trate o usuário como {prefs['address_me_as']}.")
        if prefs.get("city"):
            parts.append(f"Cidade do usuário: {prefs['city']}.")
        if prefs.get("preferred_editor"):
            parts.append(f"Editor preferido: {prefs['preferred_editor']}.")
        return " ".join(parts)
