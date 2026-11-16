"""Leitura de configuração a partir de variáveis de ambiente, validada por um modelo Pydantic do serviço."""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import ConfigError

Model = TypeVar("Model", bound=BaseModel)
LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def default_data_dir(app_folder: str, env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    """Pasta de dados por usuário: ``%LOCALAPPDATA%\\<Pasta>`` no Windows, ``~/.local/share/<pasta>`` fora dele."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / app_folder
    base = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / app_folder.lower()


def parse_bool(variable: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in ("1", "true", "sim", "yes", "on"):
        return True
    if value in ("0", "false", "nao", "não", "no", "off"):
        return False
    raise ConfigError(f"{variable} precisa ser verdadeiro ou falso (1/0, true/false, sim/não).")


def load_from_env(model: type[Model], prefix: str, env: Mapping[str, str] | None = None, **overrides: Any) -> Model:
    """Monta ``model`` com as variáveis ``<prefix><CAMPO>`` e ``overrides``. Erros dizem o campo, nunca o valor."""
    env = os.environ if env is None else env
    values: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        variable = prefix + name.upper()
        raw = env.get(variable)
        if raw is None or raw == "":
            continue
        values[name] = parse_bool(variable, raw) if field.annotation is bool else raw
    values.update(overrides)
    try:
        return model(**values)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors())
        fields = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        raise ConfigError(f"Configuração inválida — {problems}", details={"fields": fields}) from None
