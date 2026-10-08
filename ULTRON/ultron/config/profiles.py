"""Perfis de configuração.

Um perfil é um conjunto nomeado de valores aplicado antes do ``settings.json`` do usuário.
O usuário sempre pode sobrescrever qualquer campo individualmente.
"""
from __future__ import annotations

from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    # Equilíbrio padrão: local, autonomia balanceada, percepção ativa.
    "default": {},
    # Máquinas modestas: menos percepção e menos quadros por segundo.
    "performance": {
        "hud_fps": 30,
        "vision_interval": 60.0,
        "process_interval": 10.0,
        "network_interval": 60.0,
        "network_discovery": False,
        "stt_engine": "vosk-small",
        "dream_mode": False,
    },
    # Máximo isolamento: nenhuma observação de tela, nenhuma varredura de rede.
    "privacy": {
        "privacy_mode": "local",
        "allow_external_models": False,
        "screen_observation": False,
        "network_discovery": False,
    },
    # Sem voz nem efeitos sonoros (escritório, reuniões).
    "silent": {
        "voice_enabled": False,
        "sound_effects": False,
    },
    # Desenvolvimento: mais autonomia para tarefas reversíveis e logs detalhados.
    "developer": {
        "autonomy_level": "autonomous",
        "debug": True,
    },
}


def names() -> list[str]:
    return sorted(PROFILES)


def get(name: str) -> dict[str, Any]:
    return dict(PROFILES.get(str(name or "default"), {}))
