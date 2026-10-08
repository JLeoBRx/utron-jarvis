"""Arquitetura de plugins do ULTRON."""
from .base import CapabilityError, Plugin, PluginContext
from .manager import PluginManager

__all__ = ["CapabilityError", "Plugin", "PluginContext", "PluginManager"]
