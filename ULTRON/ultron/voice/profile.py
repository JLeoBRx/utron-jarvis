"""Perfil de voz efetivo.

O timbre do JARVIS é definido em ``personality/voice_profile.py`` (personalidade); este
módulo combina esse perfil com as preferências do usuário (volume e velocidade) e o
descreve de forma legível para a HUD e o diagnóstico.
"""
from __future__ import annotations

from typing import Any

from ..personality.voice_profile import JARVIS, NEUTRAL, ULTRON, VoiceProfile

PRESETS = {"jarvis": JARVIS, "neutral": NEUTRAL, "ultron": ULTRON}


def effective_profile(settings: Any = None, preset: str | None = None) -> VoiceProfile:
    preset = preset or str(getattr(settings, "voice_profile", "jarvis") or "jarvis")
    base = PRESETS.get(preset, JARVIS)
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
