"""Credenciais de serviços externos — NUNCA em arquivos de configuração nem em logs.

Ordem de leitura: variável de ambiente (ex.: ``OPENAI_API_KEY``, como no JARVIS original) e, se não
houver, o cofre do sistema operacional pelo ``keyring`` (no Windows, o Gerenciador de Credenciais).
Gravar só é possível no cofre do sistema; sem ``keyring``, a orientação é usar a variável de ambiente.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("ultron.credentials")

SERVICE = "JARVIS"
ENV_NAMES = {"openai_api_key": "OPENAI_API_KEY"}


def _keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def get_secret(name: str) -> str:
    env = ENV_NAMES.get(name)
    if env and os.environ.get(env):
        return os.environ[env].strip()
    ring = _keyring()
    if ring is None:
        return ""
    try:
        return (ring.get_password(SERVICE, name) or "").strip()
    except Exception as exc:                       # cofre indisponível: nunca derruba o JARVIS
        log.info("cofre de credenciais indisponível: %s", type(exc).__name__)
        return ""


def source(name: str) -> str:
    """De onde a credencial vem (para a interface): 'ambiente', 'cofre do sistema' ou ''."""
    env = ENV_NAMES.get(name)
    if env and os.environ.get(env):
        return "ambiente"
    ring = _keyring()
    try:
        if ring is not None and ring.get_password(SERVICE, name):
            return "cofre do sistema"
    except Exception:
        pass
    return ""


def set_secret(name: str, value: str) -> str:
    """Grava no cofre do sistema. Devolve onde ficou; levanta RuntimeError se não houver cofre."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("credencial vazia")
    ring = _keyring()
    if ring is None:
        raise RuntimeError("o pacote keyring não está instalado; use a variável de ambiente "
                           f"{ENV_NAMES.get(name, name.upper())}")
    ring.set_password(SERVICE, name, value)
    return "cofre do sistema"


def delete_secret(name: str) -> bool:
    ring = _keyring()
    if ring is None:
        return False
    try:
        ring.delete_password(SERVICE, name)
        return True
    except Exception:
        return False


def mask(value: str) -> str:
    """Forma segura de exibir: só os 4 últimos caracteres."""
    value = str(value or "")
    return ("•" * 8 + value[-4:]) if len(value) > 8 else ("•" * len(value))
