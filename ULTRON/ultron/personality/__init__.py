"""Personalidade do JARVIS — separada da lógica do sistema."""
from . import behavior, dialogue, identity, response_style, voice_profile
from .dialogue import say
from .response_style import short_for_voice, stylize

__all__ = ["behavior", "dialogue", "identity", "response_style", "voice_profile",
           "say", "stylize", "short_for_voice"]
