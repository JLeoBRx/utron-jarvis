"""PROACTIVE INTELLIGENCE — o ULTRON percebe e se antecipa, sem agir por conta própria.

Entradas: hipóteses da fusão de percepção (``PERCEPTION_FUSED``, nunca um sensor isolado),
mudanças de rede (``NETWORK_CHANGED``) e dispositivos novos na rede local
(``DEVICE_DETECTED``).

Saída: ``INSIGHT`` com texto curto no estilo do ULTRON e, quando faz sentido, uma
*sugestão* (comando ou skill). A sugestão só é executada se o usuário aceitar; se a ação
for sensível, o texto da sugestão descreve a ação e suas consequências, e a aceitação vale
como autorização apenas para aquela ação exata.

Disciplina: limiar de confiança (Decision Engine), recarga por assunto, no máximo um
insight por minuto e silêncio enquanto o usuário está no meio de outra interação.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..cognition.decision_engine import DecisionEngine
from ..core.events import EventType

log = logging.getLogger("ultron.proactive")

TOPIC_COOLDOWN = 600.0          # o mesmo assunto não é repetido por 10 minutos
GLOBAL_GAP = 60.0               # no máximo um insight por minuto
BUSY_STATES = {"THINKING", "PLANNING", "EXECUTING", "VERIFYING", "RECOVERY", "AWAITING_AUTHORIZATION",
               "LISTENING", "IMAGINING", "SIMULATING"}


@dataclass
class Insight:
    kind: str
    text: str
    priority: str = "normal"                    # low | normal | high
    action: str = "inform"                      # inform | suggest | authorize
    suggestion: dict | None = None              # {"command": str} | {"skill": str, "args": dict}
    confidence: float = 0.0
    sources: list = field(default_factory=list)
    topic: str = ""
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hung_insight(top: dict, decision) -> Insight:
    data = top.get("data", {})
    app = (top.get("description") or "").replace(" não está respondendo.", "") or data.get("process") or "aplicativo"
    process = data.get("process") or app
    if decision.action == "inform":
        return Insight("application_hung", f"{app} não está respondendo.", decision.priority, "inform",
                       topic=f"hung:{process}")
    return Insight("application_hung",
                   f"{app} não está respondendo. Posso encerrá-lo à força; dados não salvos serão perdidos. Autoriza?",
                   decision.priority, "authorize", {"skill": "app.terminate", "args": {"name": process}},
                   topic=f"hung:{process}")


def _dependency_insight(top: dict, decision) -> Insight:
    module = top.get("data", {}).get("module") or ""
    what = f"módulo {module} ausente" if module else "falha de importação"
    if decision.action == "inform":
        return Insight("dependency_error", f"Detectei uma falha de importação: {what}.", decision.priority,
                       "inform", topic=f"dep:{module}")
    return Insight("dependency_error", f"Falha de importação no projeto: {what}. Posso diagnosticar e corrigir.",
                   decision.priority, "suggest",
                   {"command": f"diagnostique e corrija a falha de importação do módulo {module}" if module
                    else "diagnostique o erro do projeto"}, topic=f"dep:{module}")


def _visible_error_insight(top: dict, decision) -> Insight:
    app = top.get("data", {}).get("application") or "aplicação ativa"
    text = f"Há um erro visível em {app}."
    suggestion = None
    if decision.action == "suggest":
        text += " Posso analisar."
        suggestion = {"command": "analise o erro que está na tela"}
    return Insight("visible_error", text, decision.priority, decision.action if suggestion else "inform",
                   suggestion, topic=f"error:{app}")


def _network_insight(top: dict, decision) -> Insight:
    return Insight("network_problem", "Conectividade de rede perdida. Posso diagnosticar.", decision.priority,
                   "suggest", {"command": "diagnostique a rede"}, topic="network")


BUILDERS: dict[str, Callable[[dict, Any], Insight]] = {
    "application_hung": _hung_insight,
    "dependency_error": _dependency_insight,
    "visible_error": _visible_error_insight,
    "network_problem": _network_insight,
}
SENSITIVE_FIX = {"application_hung"}             # a correção natural exige ação sensível


class ProactiveIntelligence:
    name = "proactive"

    def __init__(self, *, bus, state=None, decisions: DecisionEngine | None = None,
                 settings_getter: Callable[[], Any] | None = None, clock: Callable[[], float] = time.time):
        self._bus = bus
        self._state = state
        self._decisions = decisions or DecisionEngine()
        self._settings = settings_getter or (lambda: None)
        self._clock = clock
        self._lock = threading.Lock()
        self._topics: dict[str, float] = {}
        self._last_insight = 0.0
        self._subs: list = []
        self._known_devices: set[str] = set()
        self._network_online: bool | None = None
        self.history: list[dict] = []
        self.suppressed = 0

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self._state is not None:
            online = (self._state.get("network_state") or {}).get("online")
            self._network_online = None if online is None else bool(online)
        self._subs = [
            self._bus.subscribe(EventType.PERCEPTION_FUSED, self._on_fused, name="proactive.fused"),
            self._bus.subscribe(EventType.NETWORK_CHANGED, self._on_network, name="proactive.network"),
            self._bus.subscribe(EventType.DEVICE_DETECTED, self._on_device, name="proactive.device"),
        ]

    def stop(self) -> None:
        for sub in self._subs:
            sub.unsubscribe()
        self._subs = []

    def health(self) -> dict:
        enabled = getattr(self._settings(), "proactive", True)
        return {"status": "OK" if enabled else "WARN",
                "detail": f"{len(self.history)} insight(s), {self.suppressed} suprimido(s)" if enabled else "desativada"}

    # ------------------------------------------------------------ regras
    def _enabled(self) -> bool:
        return bool(getattr(self._settings(), "proactive", True))

    def _busy(self) -> bool:
        return self._state is not None and self._state.runtime_state in BUSY_STATES

    def _emit(self, insight: Insight, *, bypass_gap: bool = False) -> bool:
        now = self._clock()
        with self._lock:
            last_topic = self._topics.get(insight.topic or insight.kind, 0.0)
            if now - last_topic < TOPIC_COOLDOWN or (not bypass_gap and now - self._last_insight < GLOBAL_GAP):
                self.suppressed += 1
                return False
            self._topics[insight.topic or insight.kind] = now
            self._last_insight = now
            self.history.append(insight.to_dict())
            del self.history[:-50]
        log.info("insight %s: %s", insight.kind, insight.text)
        self._bus.publish(EventType.INSIGHT, insight.to_dict(), source="proactive")
        return True

    def evaluate(self, context: dict) -> Insight | None:
        """Transforma o contexto fundido em insight (ou nada). Não publica."""
        top = context.get("top")
        if not top:
            return None
        builder = BUILDERS.get(top.get("kind", ""))
        if builder is None:
            return None
        decision = self._decisions.decide_insight(top, sensitive_action=top.get("kind") in SENSITIVE_FIX)
        if decision.action == "ignore":
            return None
        insight = builder(top, decision)
        insight.confidence = float(top.get("confidence", 0.0))
        insight.sources = list(top.get("sources", []))
        return insight

    # ------------------------------------------------------------ eventos
    def _on_fused(self, event) -> None:
        if not self._enabled():
            return
        insight = self.evaluate(event.payload)
        if insight is None:
            return
        if self._busy() and insight.priority != "high":
            self.suppressed += 1                              # o usuário está no meio de outra interação
            return
        self._emit(insight, bypass_gap=insight.priority == "high")

    def _on_network(self, event) -> None:
        if not self._enabled():
            return
        online = bool(event.get("online"))
        previous, self._network_online = self._network_online, online
        if previous is True and not online:
            self._emit(Insight("network_problem", "Conectividade de rede perdida. Posso diagnosticar.", "high",
                               "suggest", {"command": "diagnostique a rede"}, 1.0, ["network"], "network"),
                       bypass_gap=True)
        elif previous is False and online:
            self._emit(Insight("network_restored", "Rede restabelecida.", "low", "inform", None, 1.0, ["network"],
                               "network-restored"))

    def _on_device(self, event) -> None:
        if not self._enabled() or event.get("origin") == "peripheral":
            return
        ident = event.get("mac") or event.get("ip")
        if not ident or ident in self._known_devices:
            return
        self._known_devices.add(ident)
        if not event.get("new", True):
            return
        label = event.get("hostname") or event.get("vendor") or event.get("kind") or "desconhecido"
        self._emit(Insight("device_new", f"Novo dispositivo na rede local: {event.get('ip')} ({label}).", "low",
                           "inform", None, 0.9, ["network"], f"device:{ident}"))
