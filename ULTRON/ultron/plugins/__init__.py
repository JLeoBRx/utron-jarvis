"""Arquitetura de plugins do SAFRA."""
from .base import CapabilityError, Plugin, PluginContext
from .manager import PluginManager

__all__ = ["CapabilityError", "Plugin", "PluginContext", "PluginManager"]
