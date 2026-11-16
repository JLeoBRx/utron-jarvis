"""Integrações específicas do sistema operacional."""
from . import system, win32
from .system import IS_WINDOWS

__all__ = ["system", "win32", "IS_WINDOWS"]
