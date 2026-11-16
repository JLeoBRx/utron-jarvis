"""Preferências do usuário: só as chaves conhecidas, cada uma validada. Origem gravada (declarada pelo usuário)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from safra_foundation import errors

from ..storage.models import Preference, utcnow

PREFERENCES: dict[str, dict[str, Any]] = {
    "nome": {"label": "Seu nome", "default": "", "max": 60},
    "tratamento": {"label": "Como o SAFRA se dirige a você", "default": "", "max": 40},
    "movimento_reduzido": {"label": "Movimento reduzido", "default": False},
    "densidade": {"label": "Densidade da interface", "default": "confortavel", "choices": ["confortavel", "compacta"]},
    "tamanho_texto": {"label": "Tamanho do texto", "default": "normal", "choices": ["normal", "grande"]},
}


def _validate(key: str, value: Any) -> Any:
    spec = PREFERENCES.get(key)
    if spec is None:
        raise errors.NotFound("Preferência desconhecida.")
    default = spec["default"]
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise errors.InvalidInput("Esta preferência é sim ou não.")
        return value
    if not isinstance(value, str):
        raise errors.InvalidInput("Esta preferência é um texto.")
    value = value.strip()
    if "choices" in spec and value not in spec["choices"]:
        raise errors.InvalidInput("Valor fora das opções: " + ", ".join(spec["choices"]) + ".")
    if "max" in spec and len(value) > spec["max"]:
        raise errors.InvalidInput(f"Use no máximo {spec['max']} caracteres.")
    return value


def get_preferences(db: Session) -> dict[str, Any]:
    stored = {p.key: p for p in db.scalars(select(Preference).where(Preference.key.in_(list(PREFERENCES))))}
    result = {}
    for key, spec in PREFERENCES.items():
        row = stored.get(key)
        result[key] = {"label": spec["label"], "value": row.value if row else spec["default"], "default": spec["default"],
                       "choices": spec.get("choices"), "source": row.source if row else "padrao",
                       "updated_at": row.updated_at.isoformat() if row else None}
    return result


def set_preference(db: Session, key: str, value: Any) -> dict[str, Any]:
    value = _validate(key, value)
    row = db.get(Preference, key)
    if row is None:
        db.add(Preference(key=key, value=value, source="user"))
    else:
        row.value, row.source, row.updated_at = value, "user", utcnow()
    db.flush()
    return get_preferences(db)[key]
