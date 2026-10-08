"""
J.A.R.V.I.S. // Fase 8 — Motor Conversacional

Gerencia o estado curto da conversa por voz: janela de continuação sem wake-word,
barge-in (interrupção da fala), comandos de silêncio/cancelamento e métricas simples.
Não toma decisões de segurança e não executa ferramentas.
"""
import re
import threading
import time
import unicodedata

FOLLOWUP_SECONDS = 14.0
WAKE_REQUIRED_AFTER_SECONDS = 30.0

_CANCEL = {
    "pare", "parar", "para", "pare tudo", "parar tudo", "cancele", "cancelar",
    "aborta", "abortar", "silencio", "silêncio", "cale a boca"
}


def _norm(text):
    value = unicodedata.normalize("NFD", str(text).casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(value.split())


class ConversationEngine:
    def __init__(self, log=print):
        self.log = log
        self._lock = threading.Lock()
        self._followup_until = 0.0
        self._last_wake = 0.0
        self._turns = 0
        self._muted_until = 0.0

    def wake(self):
        with self._lock:
            self._last_wake = time.monotonic()
            self._followup_until = self._last_wake + FOLLOWUP_SECONDS
            self._turns = 0

    def touch(self):
        with self._lock:
            now = time.monotonic()
            self._followup_until = now + FOLLOWUP_SECONDS
            self._turns += 1

    def is_followup(self):
        with self._lock:
            return time.monotonic() <= self._followup_until

    def require_wake(self):
        with self._lock:
            return time.monotonic() > self._followup_until

    def classify(self, text):
        """Retorna cancel/silence/normal para priorizar barge-in."""
        normalized = _norm(text)
        if normalized in _CANCEL:
            return "cancel"
        if normalized.startswith("jarvis "):
            return "wake_command"
        return "normal"

    def muted(self):
        with self._lock:
            return time.monotonic() < self._muted_until

    def mute(self, seconds=10.0):
        with self._lock:
            self._muted_until = max(self._muted_until, time.monotonic() + seconds)

    def status(self):
        with self._lock:
            now = time.monotonic()
            return {
                "followup_active": now <= self._followup_until,
                "seconds_remaining": max(0.0, self._followup_until - now),
                "turns": self._turns,
                "muted": now < self._muted_until,
            }


engine = ConversationEngine()
