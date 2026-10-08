"""Perfil de voz efetivo.

O timbre do ULTRON é definido em ``personality/voice_profile.py`` (personalidade); este
módulo combina esse perfil com as preferências do usuário (volume e velocidade) e o
descreve de forma legível para a HUD e o diagnóstico.
"""
from __future__ import annotations

from typing import Any

from ..personality.voice_profile import NEUTRAL, ULTRON, VoiceProfile

PRESETS = {"ultron": ULTRON, "neutral": NEUTRAL}


def effective_profile(settings: Any = None, preset: str = "ultron") -> VoiceProfile:
    base = PRESETS.get(preset, ULTRON)
    if settings is None:
        return base
    return base.with_user(volume=getattr(settings, "volume", None), speed=getattr(settings, "speech_speed", None))


def describe(profile: VoiceProfile) -> dict[str, str]:
    return {
        "altura": f"{(profile.pitch - 1.0) * 100:+.0f}%",
        "velocidade": f"{profile.speed:.2f}x",
        "rouquidão": f"{profile.rasp:.0%}",
        "graves": f"{profile.depth_db:+.1f} dB",
        "corte de agudos": f"{profile.air_cut_hz / 1000:.1f} kHz",
        "volume": f"{profile.volume:.0%}",
    }
