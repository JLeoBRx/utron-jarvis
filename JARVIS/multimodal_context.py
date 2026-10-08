"""J.A.R.V.I.S. // MULTIMODAL CONTEXT (Fase 29)
Unifica sinais de tela, UI, janela, voz/texto e World Model em evidência segura.
"""
from __future__ import annotations
import time

def build(*, observation=None, foreground=None, transcript="", world=None, windows=None, conversation=None):
    observation=dict(observation or {}); foreground=dict(foreground or {}); windows=dict(windows or {})
    world=dict(world or {})
    return {
        "timestamp": time.time(),
        "visual": observation,
        "foreground": foreground,
        "windows": windows,
        "voice": {"transcript": str(transcript or "")[:1200]},
        "conversation": list(conversation or [])[-8:],
        "world_model": world,
        "signals": {
            "window_available": bool(windows.get("available")),
            "visual_available": bool(observation),
            "voice_available": bool(transcript),
            "context_change": bool((observation.get("evidencia_tela") or {}).get("context_change")),
            "error_visible": bool(observation.get("erro_visivel") or observation.get("erro_texto")),
        },
    }
