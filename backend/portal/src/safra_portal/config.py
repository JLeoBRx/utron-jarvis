"""Configuração do processo do Portal: variáveis ``SAFRA_PORTAL_*``. Nenhum segredo é lido daqui além da URL
do banco, que em produção deve vir do ambiente do servidor e nunca do repositório."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from safra_foundation.settings import default_data_dir, load_from_env

ENV_PREFIX = "SAFRA_PORTAL_"
DATA_FOLDER = "SAFRA-Portal"
DEFAULT_PORT = 47900


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["development", "test", "staging", "production"] = "development"
    data_dir: Path = Field(default_factory=lambda: default_data_dir(DATA_FOLDER))
    database_url: str = ""
    media_dir: Path | None = None
    admin_dist: Path | None = None                  # painel compilado (apps/admin/dist); detectado se vazio
    host: str = "127.0.0.1"
    port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    public_base_url: str = ""                       # endereço público do site, sem barra no fim
    extra_allowed_hosts: str = ""                   # nomes adicionais aceitos em Host, separados por vírgula
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_to_file: bool = True
    migrate_on_start: bool = True
    seed_on_start: bool = True
    session_idle_minutes: int = Field(default=30, ge=5, le=240)
    session_absolute_hours: int = Field(default=12, ge=1, le=72)
    recovery_token_minutes: int = Field(default=30, ge=5, le=120)
    login_attempts_per_ip: int = Field(default=10, ge=3, le=100)       # por janela de 5 minutos
    lockout_threshold: int = Field(default=5, ge=3, le=20)             # falhas seguidas até bloquear a conta
    lockout_minutes: int = Field(default=15, ge=1, le=1440)
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=64 * 1024, le=50 * 1024 * 1024)

    @field_validator("public_base_url")
    @classmethod
    def _clean_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value:
            parts = urlsplit(value)
            if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
                raise ValueError("use um endereço como https://exemplo.com, sem caminho")
        return value

    @model_validator(mode="after")
    def _derive_and_check(self) -> "Settings":
        if not self.database_url:
            object.__setattr__(self, "database_url", "sqlite:///" + (self.data_dir / "portal.sqlite3").as_posix())
        if self.media_dir is None:
            object.__setattr__(self, "media_dir", self.data_dir / "media")
        if not self.public_base_url:
            object.__setattr__(self, "public_base_url", f"http://127.0.0.1:{self.port}")
        if self.environment == "production":
            if self.database_url.startswith("sqlite:"):
                raise ValueError("em produção o Portal usa PostgreSQL; SQLite é só para desenvolvimento e teste")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("em produção o endereço público precisa ser HTTPS")
        return self

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def secure_cookies(self) -> bool:
        return self.public_base_url.startswith("https://")

    @property
    def origin(self) -> str:
        parts = urlsplit(self.public_base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        hosts = {urlsplit(self.public_base_url).netloc.lower()}
        hosts.update(h.strip().lower() for h in self.extra_allowed_hosts.split(",") if h.strip())
        if self.environment != "production":
            hosts.update(f"{name}:{self.port}" for name in ("127.0.0.1", "localhost"))
        return tuple(sorted(hosts))

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        origins = {self.origin}
        if self.environment != "production":
            origins.update(f"http://{name}:{self.port}" for name in ("127.0.0.1", "localhost"))
        return tuple(sorted(origins))


def load_settings(env: Mapping[str, str] | None = None, **overrides: Any) -> Settings:
    import os
    env = os.environ if env is None else env
    if not env.get(ENV_PREFIX + "DATA_DIR") and "data_dir" not in overrides:
        overrides["data_dir"] = default_data_dir(DATA_FOLDER, env)
    return load_from_env(Settings, ENV_PREFIX, env, **overrides)
