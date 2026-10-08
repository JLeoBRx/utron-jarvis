"""Modo de privacidade local e monitor de conexões."""
from .connections import ConnectionMonitor, classify, firewall_status
from .privacy_mode import ExternalDecision, PrivacyPolicy

__all__ = ["ConnectionMonitor", "classify", "firewall_status", "ExternalDecision", "PrivacyPolicy"]
