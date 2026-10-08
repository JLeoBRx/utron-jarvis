"""Contrato de plugins do ULTRON.

Um plugin declara ``name``, ``version``, ``capabilities`` e ``requirements`` e implementa
``initialize(ctx)`` e ``shutdown()``. Ele só pode usar o que declarou:

* ``skills``          registrar skills (passam pelo mesmo controle de risco/autorização);
* ``health``          registrar verificações no Health Monitor;
* ``events``          assinar eventos do Event Bus;
* ``model_provider``  oferecer um modelo alternativo — só usado se a privacidade permitir
  modelos externos, e cada chamada é registrada como conexão externa.

Tudo o que um plugin registra é removido no ``shutdown``. Plugins são código local
carregado das pastas de plugins; o ULTRON não baixa plugins.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

CAPABILITIES = ("skills", "health", "events", "model_provider")


class CapabilityError(PermissionError):
    """O plugin tentou usar algo que não declarou em ``capabilities``."""


class Plugin:
    name: str = "plugin"
    version: str = "0.1.0"
    description: str = ""
    capabilities: tuple = ()
    requirements: dict = {}          # {"modules": [...], "platform": "win32", "ultron": "1.0"}
    default_enabled: bool = True     # False: só carrega se listado em settings.plugins_enabled

    def initialize(self, ctx: "PluginContext") -> None:  # pragma: no cover - contrato
        raise NotImplementedError

    def shutdown(self) -> None:
        pass

    def health(self) -> dict:
        return {"status": "OK", "detail": f"{self.name} {self.version}"}


@dataclass
class PluginContext:
    plugin: Plugin
    bus: Any = None
    state: Any = None
    settings: Callable[[], Any] | None = None
    registry: Any = None
    health_monitor: Any = None
    router: Any = None
    privacy: Any = None
    data_dir: Path | None = None
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("ultron.plugin"))
    _skills: list = field(default_factory=list)
    _subs: list = field(default_factory=list)
    _health: list = field(default_factory=list)
    _providers: list = field(default_factory=list)

    def _require(self, capability: str) -> None:
        if capability not in self.plugin.capabilities:
            raise CapabilityError(f"plugin {self.plugin.name} não declarou a capacidade '{capability}'")

    # ------------------------------------------------------------ registros
    def register_skill(self, skill) -> None:
        self._require("skills")
        if not str(skill.name).startswith("plugin."):
            raise ValueError("skills de plugin usam o prefixo 'plugin.'")
        self.registry.register(skill)
        self._skills.append(skill.name)

    def register_health(self, name: str, probe: Callable[[], dict]) -> None:
        self._require("health")
        key = f"PLUGIN:{self.plugin.name}:{name}".upper()
        self.health_monitor.register(key, probe)
        self._health.append(key)

    def subscribe(self, types, handler) -> None:
        self._require("events")
        self._subs.append(self.bus.subscribe(types, handler, name=f"plugin.{self.plugin.name}"))

    def register_model_provider(self, name: str, provider) -> None:
        self._require("model_provider")
        self.router.register_provider(name, _GuardedProvider(name, provider, self.privacy))
        self._providers.append(name)

    def setting(self, key: str, default: Any = None) -> Any:
        return getattr(self.settings(), key, default) if self.settings else default

    def cleanup(self) -> None:
        for sub in self._subs:
            sub.unsubscribe()
        for name in self._skills:
            try:
                self.registry.unregister(name)
            except KeyError:
                pass
        for key in self._health:
            unregister = getattr(self.health_monitor, "unregister", None)
            if unregister:
                unregister(key)
        for name in self._providers:
            remove = getattr(self.router, "unregister_provider", None)
            if remove:
                remove(name)
        self._subs, self._skills, self._health, self._providers = [], [], [], []


class _GuardedProvider:
    """Envolve um provedor externo: cada chamada passa pela política de privacidade."""

    def __init__(self, name: str, provider, privacy):
        self.name = name
        self._provider = provider
        self._privacy = privacy
        self.tasks = getattr(provider, "tasks", ("text",))
        self.model = getattr(provider, "model", name)

    def available(self) -> bool:
        return bool(self._provider.available())

    def chat(self, messages: list[dict], **kwargs: Any):
        if self._privacy is not None:
            decision = self._privacy.allow_external(f"modelo externo {self.name}", getattr(self._provider, "endpoint", ""))
            if not decision.allowed:
                raise PermissionError(f"modelo externo bloqueado: {decision.reason}")
        return self._provider.chat(messages, **kwargs)
