"""Configuração do SAFRA: ``settings`` (valores), ``profiles`` (presets) e ``paths``."""
from . import paths, profiles
from .settings import Settings, SettingsManager, get, manager

__all__ = ["Settings", "SettingsManager", "get", "manager", "paths", "profiles"]
