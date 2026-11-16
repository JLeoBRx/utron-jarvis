"""Configuração do processo do Assistant: variáveis ``SAFRA_*``, validadas antes de qualquer outra coisa.

Aqui só entra o que o processo precisa para subir. Preferências do usuário ficam no banco. Segredos nunca
passam por aqui: ficam no cofre do sistema.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from safra_foundation.settings import LOOPBACK_HOSTS, default_data_dir, load_from_env

ENV_PREFIX = "SAFRA_"
DATA_FOLDER = "SAFRA"                # pasta NOVA: a do legado nunca é alterada (AD-11)
DEFAULT_PORT = 47800


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["development", "test", "staging", "production"] = "development"
    data_dir: Path = Field(default_factory=lambda: default_data_dir(DATA_FOLDER))
    database_url: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_to_file: bool = True
    migrate_on_start: bool = True
    ui_dist: Path | None = None          # interface compilada; sem valor, procura no pacote e no repositório

    @field_validator("api_host")
    @classmethod
    def _only_loopback(cls, value: str) -> str:
        # O Assistant nunca é exposto na rede: o acesso remoto fica desligado (AD-12).
        if value not in LOOPBACK_HOSTS:
            raise ValueError("a API do Assistant só pode escutar neste computador (127.0.0.1, ::1 ou localhost)")
        return value

    @field_validator("database_url")
    @classmethod
    def _only_local_database(cls, value: str) -> str:
        # O banco do Assistant é privado e local: nunca um servidor de banco compartilhado.
        if value and not value.startswith("sqlite:"):
            raise ValueError("o banco do Assistant é um arquivo SQLite local; servidores de banco não são aceitos")
        return value

    @model_validator(mode="after")
    def _derive_database_url(self) -> "Settings":
        if not self.database_url:
            object.__setattr__(self, "database_url", "sqlite:///" + (self.data_dir / "safra.sqlite3").as_posix())
        return self

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        """Valores aceitos no cabeçalho ``Host`` (defesa contra *DNS rebinding*)."""
        return tuple(f"{name}:{self.api_port}" for name in ("127.0.0.1", "localhost", "[::1]"))

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """Origens aceitas em pedidos que alteram dados: só a própria interface, servida por este processo."""
        return tuple(f"http://{host}" for host in self.allowed_hosts)


def load_settings(env: Mapping[str, str] | None = None, **overrides: Any) -> Settings:
    import os
    env = os.environ if env is None else env
    if not env.get(ENV_PREFIX + "DATA_DIR") and "data_dir" not in overrides:
        overrides["data_dir"] = default_data_dir(DATA_FOLDER, env)
    return load_from_env(Settings, ENV_PREFIX, env, **overrides)
