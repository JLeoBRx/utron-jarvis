"""Acesso remoto: o agente da matriz-mãe que liga este JARVIS à JARVIS WEB ORB (via gateway, conexão de saída)."""
from .agent import RemoteAgent, remote_ok

__all__ = ["RemoteAgent", "remote_ok"]
