"""Autonomia e autorização.

Princípios do projeto:

* ação comum, reversível e segura → executar sem perguntar;
* ambiguidade real → perguntar (tratado na cognição);
* ação sensível → solicitar autorização explícita;
* a proatividade nunca executa nada sensível sozinha.

O ``AuthorizationManager`` mantém no máximo um pedido pendente. O usuário responde por voz
("sim"/"não"), por texto ou pela HUD. Pedidos expiram (padrão 30 s) e expiração = negação.
"""
from __future__ import annotations

import itertools
import json
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from ..skills.base import Risk

ORIGINS = ("user", "plan", "agent", "recovery", "proactive", "automation")

# Categorias que exigem autorização ESPECÍFICA (ação + recurso + escopo), qualquer que seja o nível de
# autonomia ou a origem do pedido. A aprovação vale uma única vez para exatamente aquela chamada.
SENSITIVE = {
    "permanent_delete": "exclusão permanente de dados",
    "system_config": "alteração crítica de configuração do sistema",
    "admin_command": "comando administrativo",
    "security": "alteração de firewall ou de proteções do sistema",
    "network_admin": "administração de dispositivo de rede",
    "data_egress": "envio de dados para fora do computador",
    "credentials": "acesso a credenciais ou informação sensível",
    "third_party": "ação irreversível ou que afeta terceiros",
}


@dataclass
class AutonomyDecision:
    action: str                 # execute | authorize | refuse
    reason: str
    risk: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomyPolicy:
    def __init__(self, settings_getter: Callable[[], Any]):
        self._settings = settings_getter

    @property
    def level(self) -> str:
        return getattr(self._settings(), "autonomy_level", "balanced")

    def decide(self, risk: Risk, *, reversible: bool, origin: str, sensitive: str = "") -> AutonomyDecision:
        level = self.level
        r = risk.level
        if sensitive:
            label = SENSITIVE.get(sensitive, sensitive)
            return AutonomyDecision("authorize", f"exige autorização específica: {label}", risk.value)
        if origin == "proactive" and r > Risk.LOW.level:
            return AutonomyDecision("authorize", "ação iniciada proativamente exige autorização", risk.value)
        if r >= Risk.HIGH.level:
            return AutonomyDecision("authorize", "ação sensível", risk.value)
        if r == Risk.NONE.level:
            return AutonomyDecision("execute", "somente leitura", risk.value)
        if level == "restricted":
            if r == Risk.LOW.level and origin in ("user", "automation"):
                return AutonomyDecision("execute", "pedido direto de baixo risco", risk.value)
            return AutonomyDecision("authorize", "modo restrito", risk.value)
        if r == Risk.LOW.level:
            return AutonomyDecision("execute", "baixo risco e reversível", risk.value)
        # MEDIUM
        if reversible or origin in ("user", "automation") or level == "autonomous":
            return AutonomyDecision("execute", "risco moderado, reversível ou pedido direto", risk.value)
        return AutonomyDecision("authorize", "risco moderado escolhido pelo agente", risk.value)


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


YES = {"sim", "confirmo", "confirma", "autorizo", "autorizado", "pode", "pode sim", "pode fazer", "afirmativo",
       "execute", "executar", "prossiga", "prosseguir", "sim senhor", "ok", "positivo", "faca", "faca isso",
       "sim pode", "pode prosseguir", "ultron sim"}
NO = {"nao", "nao autorizo", "negativo", "cancela", "cancelar", "cancele", "pare", "parar", "nao faca", "nunca",
      "esquece", "deixa", "deixa pra la", "ultron nao", "nao obrigado"}


def classify_reply(text: str) -> str | None:
    value = _norm(text)
    if value in YES:
        return "yes"
    if value in NO:
        return "no"
    words = value.split()
    if words and words[0] in ("sim", "confirmo", "autorizo") and len(words) <= 4:
        return "yes"
    if words and words[0] in ("nao", "negativo", "cancela", "cancelar") and len(words) <= 4:
        return "no"
    return None


_ids = itertools.count(1)


@dataclass
class AuthorizationRequest:
    description: str
    skill: str
    risk: str
    args: dict = field(default_factory=dict)
    category: str = ""                 # categoria sensível (SENSITIVE) — escopo exibido ao usuário
    id: int = field(default_factory=lambda: next(_ids))
    created: float = field(default_factory=time.time)
    expires: float = 0.0
    status: str = "pending"            # pending | approved | denied | expired | cancelled
    resolved_by: str = ""
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "skill": self.skill, "risk": self.risk,
                "category": self.category, "category_label": SENSITIVE.get(self.category, ""),
                "args": dict(self.args), "created": self.created, "expires": self.expires, "status": self.status,
                "resolved_by": self.resolved_by,
                "seconds_left": max(0.0, round(self.expires - time.time(), 1)) if self.status == "pending" else 0.0}


class AuthorizationManager:
    def __init__(self, *, bus=None, state=None, timeout_getter: Callable[[], float] | None = None):
        self._bus = bus
        self._state = state
        self._timeout = timeout_getter or (lambda: 30.0)
        self._lock = threading.RLock()
        self._pending: AuthorizationRequest | None = None
        self._preapproved: tuple | None = None
        self.history: list[dict] = []

    @staticmethod
    def _key(skill: str, args: dict | None) -> str:
        normalized = {str(k): str(v)[:80] for k, v in (args or {}).items()}      # mesma forma do pedido
        return skill + "|" + json.dumps(normalized, sort_keys=True, ensure_ascii=False)

    def pre_approve(self, skill: str, args: dict | None, *, ttl: float = 30.0, by: str = "user") -> None:
        """O usuário aceitou uma sugestão que descrevia exatamente esta ação (com suas
        consequências). O próximo pedido idêntico, dentro de ``ttl``, é aprovado uma única vez."""
        with self._lock:
            self._preapproved = (self._key(skill, args), time.time() + ttl, by)

    def request(self, description: str, *, skill: str, risk: str, args: dict | None = None,
                timeout: float | None = None, category: str = "") -> AuthorizationRequest:
        req = AuthorizationRequest(description, skill, risk, dict(args or {}), category)
        req.expires = time.time() + float(timeout if timeout is not None else self._timeout())
        with self._lock:
            pre, self._preapproved = self._preapproved, None
            if self._pending is not None and self._pending.status == "pending":
                self._finish(self._pending, "cancelled", "substituído")
            self._pending = req
        if pre is not None and pre[0] == self._key(skill, args) and time.time() <= pre[1]:
            self._finish(req, "approved", f"{pre[2]} (sugestão aceita)")
            return req
        self._publish_state(req)
        if self._bus is not None:
            self._bus.publish(EventType.AUTHORIZATION_REQUIRED, req.to_dict(), source="autonomy")
        return req

    def wait(self, req: AuthorizationRequest, cancel=None) -> bool:
        while req.status == "pending":
            if cancel is not None and getattr(cancel, "cancelled", False):
                self._finish(req, "cancelled", "tarefa cancelada")
                break
            remaining = req.expires - time.time()
            if remaining <= 0:
                self._finish(req, "expired", "tempo esgotado")
                break
            req._event.wait(min(0.2, remaining))
        return req.status == "approved"

    def resolve(self, approved: bool, *, by: str = "user", request_id: int | None = None) -> bool:
        with self._lock:
            req = self._pending
        if req is None or req.status != "pending" or (request_id is not None and req.id != request_id):
            return False
        self._finish(req, "approved" if approved else "denied", by)
        return True

    def handle_reply(self, text: str, *, by: str = "voice") -> str | None:
        """Consome "sim"/"não" quando há pedido pendente. Devolve 'yes', 'no' ou None."""
        if self.pending() is None:
            return None
        reply = classify_reply(text)
        if reply is not None:
            self.resolve(reply == "yes", by=by)
        return reply

    def pending(self) -> AuthorizationRequest | None:
        with self._lock:
            req = self._pending
        if req is not None and req.status == "pending" and time.time() > req.expires:
            self._finish(req, "expired", "tempo esgotado")
            return None
        return req if req is not None and req.status == "pending" else None

    def cancel_all(self) -> None:
        with self._lock:
            req = self._pending
        if req is not None and req.status == "pending":
            self._finish(req, "cancelled", "cancelado pelo usuário")

    def _finish(self, req: AuthorizationRequest, status: str, by: str) -> None:
        if req.status != "pending":
            return
        req.status = status
        req.resolved_by = by
        req._event.set()
        self.history.append(req.to_dict())
        del self.history[:-50]
        with self._lock:
            if self._pending is req:
                self._pending = None
        self._publish_state(None)
        if self._bus is not None:
            self._bus.publish(EventType.AUTHORIZATION_RESOLVED, req.to_dict(), source="autonomy")

    def _publish_state(self, req: AuthorizationRequest | None) -> None:
        if self._state is not None:
            self._state.update(_source="autonomy", pending_authorization=req.to_dict() if req else None)
