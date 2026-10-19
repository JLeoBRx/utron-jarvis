"""PRIVACY LOCAL — reduz a exposição do próprio JARVIS.

Quando ativo:

* o modelo de linguagem é sempre o Ollama local (endereços remotos são recusados);
* nenhuma conexão externa automática (em segundo plano) é permitida;
* conexões externas pedidas explicitamente pelo usuário podem ser autorizadas, e ficam
  registradas (``strict_block`` bloqueia até estas);
* o JARVIS não abre portas nem inicia servidores;
* conexões do processo são monitoradas e exibidas;
* o firewall do Windows é apenas consultado — nunca alterado; nada tenta burlar monitoramento.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..core.events import EventType
from ..models.ollama_client import is_local_url
from .connections import ConnectionMonitor, firewall_status

log = logging.getLogger("ultron.privacy")


@dataclass
class ExternalDecision:
    allowed: bool
    reason: str
    purpose: str
    target: str
    explicit: bool
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PrivacyPolicy:
    name = "privacy"

    def __init__(self, settings_getter: Callable[[], Any], *, bus=None, state=None,
                 monitor: ConnectionMonitor | None = None):
        self._settings = settings_getter
        self._bus = bus
        self._state = state
        self.monitor = monitor or ConnectionMonitor()
        self.strict_block = False
        self._decisions: deque[ExternalDecision] = deque(maxlen=200)
        self._lock = threading.Lock()
        self._firewall: dict[str, Any] = {}

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self.refresh(check_firewall=True)

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        scan = self.monitor.last_scan
        exposed = [x for x in scan.get("listening", []) if x.get("exposed")]
        if exposed:
            return {"status": "WARN", "detail": f"{len(exposed)} porta(s) em escuta"}
        return {"status": "OK", "detail": "LOCAL MODE" if self.local_mode else "modo padrão"}

    # ------------------------------------------------------------ política
    @property
    def mode(self) -> str:
        return getattr(self._settings(), "privacy_mode", "local")

    @property
    def local_mode(self) -> bool:
        return self.mode == "local"

    def external_models_allowed(self) -> bool:
        return not self.local_mode and bool(getattr(self._settings(), "allow_external_models", False))

    def ollama_is_local(self) -> bool:
        return is_local_url(getattr(self._settings(), "ollama_url", "http://127.0.0.1:11434"))

    def allow_external(self, purpose: str, target: str = "", *, explicit: bool = False) -> ExternalDecision:
        if self.strict_block:
            decision = ExternalDecision(False, "bloqueio total de conexões externas ativo", purpose, target,
                                        explicit, time.time())
        elif not self.local_mode:
            decision = ExternalDecision(True, "modo padrão", purpose, target, explicit, time.time())
        elif explicit:
            decision = ExternalDecision(True, "solicitado explicitamente pelo usuário (registrado)", purpose,
                                        target, explicit, time.time())
        else:
            decision = ExternalDecision(False, "LOCAL MODE: conexões externas automáticas bloqueadas", purpose,
                                        target, explicit, time.time())
        with self._lock:
            self._decisions.append(decision)
        log.info("conexão externa %s: %s (%s)", "permitida" if decision.allowed else "bloqueada", purpose, decision.reason)
        if self._bus is not None:
            self._bus.publish(EventType.PRIVACY_UPDATED, {"decision": decision.to_dict()}, source="privacy")
        return decision

    # ------------------------------------------------------------ observação
    def refresh(self, *, check_firewall: bool = False) -> dict[str, Any]:
        self.monitor.scan()
        if check_firewall or not self._firewall:
            try:
                self._firewall = firewall_status()
            except Exception as exc:
                self._firewall = {"available": False, "error": str(exc)}
        status = self.status()
        if self._state is not None:
            self._state.update(_source="privacy", privacy=status)
        return status

    def status(self) -> dict[str, Any]:
        scan = self.monitor.last_scan or {}
        with self._lock:
            decisions = [d.to_dict() for d in list(self._decisions)[-20:]]
        return {
            "local_mode": self.local_mode,
            "mode": self.mode,
            "ollama_local": self.ollama_is_local(),
            "external_models": self.external_models_allowed(),
            "strict_block": self.strict_block,
            "external_now": scan.get("external_now", []),
            "external_log": self.monitor.external_log()[:30],
            "network_services": scan.get("listening", []),
            "decisions": decisions,
            "firewall": self._firewall,
            "monitor_available": scan.get("available", False),
        }
