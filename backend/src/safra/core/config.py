"""Configuração do processo: lida de variáveis ``SAFRA_*``, validada antes de qualquer outra coisa.

Aqui só entra o que o processo precisa para subir (onde ficam os dados, onde a API escuta, como registra).
Preferências do usuário pertencem ao banco e chegam em fase posterior. Segredos nunca passam por aqui.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import ConfigError

ENV_PREFIX = "SAFRA_"
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")
DEFAULT_PORT = 47800


def default_data_dir(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    """Pasta de dados da nova geração. Não é a pasta do legado, que nunca é alterada (AD-11)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "SAFRA"
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "safra"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["development", "test", "staging", "production"] = "development"
    data_dir: Path = Field(default_factory=default_data_dir)
    database_url: str = ""
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=DEFAULT_PORT, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_to_file: bool = True
    migrate_on_start: bool = True

    @field_validator("api_host")
    @classmethod
    def _only_loopback(cls, value: str) -> str:
        # O acesso remoto fica desligado até existirem autenticação, autorização e TLS (AD-12).
        if value not in LOOPBACK_HOSTS:
            raise ValueError("a API só pode escutar neste computador (127.0.0.1, ::1 ou localhost); "
                             "o acesso remoto ainda não está disponível")
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
        names = ("127.0.0.1", "localhost", "[::1]")
        return tuple(f"{name}:{self.api_port}" for name in names)


def _parse_bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in ("1", "true", "sim", "yes", "on"):
        return True
    if value in ("0", "false", "nao", "não", "no", "off"):
        return False
    raise ConfigError(f"{ENV_PREFIX}{name.upper()} precisa ser verdadeiro ou falso (1/0, true/false, sim/não).")


def load_settings(env: Mapping[str, str] | None = None, **overrides: Any) -> Settings:
    """Monta a configuração a partir de ``SAFRA_*`` e de ``overrides``. Erros dizem o campo, nunca o valor."""
    env = os.environ if env is None else env
    values: dict[str, Any] = {}
    for name, field in Settings.model_fields.items():
        raw = env.get(ENV_PREFIX + name.upper())
        if raw is None or raw == "":
            continue
        values[name] = _parse_bool(name, raw) if field.annotation is bool else raw
    if "data_dir" not in values and "data_dir" not in overrides:
        values["data_dir"] = default_data_dir(env)
    values.update(overrides)
    try:
        return Settings(**values)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors())
        raise ConfigError(f"Configuração inválida — {problems}",
                          details={"fields": sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})}) from None
