"""Dynamic Model Router.

Consulta o Ollama (``/api/tags`` e ``/api/show``) para saber quais modelos existem de fato
e escolhe um por tarefa:

* ``text``   — preferência ``qwen2.5:3b``;
* ``vision`` — preferência ``qwen2.5vl:3b``.

Nunca presume disponibilidade: se nenhum modelo adequado existir, a seleção vem marcada
como indisponível, com a instrução exata para instalar. Provedores externos (plugins)
só são considerados quando o modo de privacidade permite.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from .ollama_client import ChatResult, ModelInfo, OllamaClient, OllamaError

log = logging.getLogger("ultron.router")

PREFERENCES: dict[str, tuple[str, ...]] = {
    "text": ("qwen2.5:3b", "qwen2.5:7b", "qwen2.5", "qwen3", "llama3.2", "llama3.1", "gemma3",
             "mistral", "phi4", "phi3"),
    "vision": ("qwen2.5vl:3b", "qwen2.5vl:7b", "qwen2.5vl", "llama3.2-vision", "llava",
               "minicpm-v", "gemma3", "moondream", "bakllava"),
}
VISION_HINTS = ("vl", "vision", "llava", "minicpm-v", "moondream", "bakllava")
EMBED_HINTS = ("embed", "nomic", "bge", "mxbai", "minilm")


@dataclass
class Selection:
    task: str
    model: str | None
    available: bool
    reason: str
    provider: str = "ollama"
    install_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"task": self.task, "model": self.model, "available": self.available,
                "reason": self.reason, "provider": self.provider, "install_hint": self.install_hint}


class ModelUnavailable(RuntimeError):
    def __init__(self, selection: Selection):
        super().__init__(selection.reason)
        self.selection = selection


@dataclass
class RouterStatus:
    ollama_alive: bool = False
    version: str = ""
    installed: list = field(default_factory=list)
    selections: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    latency_ms: float | None = None
    checked_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ollama_alive": self.ollama_alive, "version": self.version,
                "installed": list(self.installed), "missing": list(self.missing),
                "selections": {k: v.to_dict() for k, v in self.selections.items()},
                "latency_ms": self.latency_ms, "checked_at": self.checked_at, "error": self.error}


def _base(name: str) -> str:
    return name.split(":", 1)[0].lower()


def _matches(installed: str, wanted: str) -> bool:
    inst, want = installed.lower(), wanted.lower()
    if inst == want or inst == want + ":latest":
        return True
    if ":" not in want:          # preferência por família ("qwen2.5" casa "qwen2.5:7b")
        return _base(inst) == want
    return False


class ModelRouter:
    def __init__(self, client: OllamaClient, *, settings_getter: Callable[[], Any],
                 bus=None, state=None, privacy=None, cache_seconds: float = 30.0):
        self.client = client
        self._settings = settings_getter
        self._bus = bus
        self._state = state
        self._privacy = privacy
        self._cache_seconds = cache_seconds
        self._lock = threading.RLock()
        self._models: list[ModelInfo] = []
        self._caps: dict[str, tuple] = {}
        self._status = RouterStatus()
        self._selected: dict[str, str | None] = {}
        self._providers: dict[str, Any] = {}

    # ------------------------------------------------------------ descoberta
    def refresh(self, *, force: bool = False) -> RouterStatus:
        with self._lock:
            if not force and time.time() - self._status.checked_at < self._cache_seconds:
                return self._status
        status = RouterStatus(checked_at=time.time())
        try:
            models = self.client.list_models()
            status.ollama_alive = True
            status.latency_ms = self.client.last_latency_ms
            try:
                status.version = self.client.version()
            except OllamaError:
                status.version = ""
        except OllamaError as exc:
            models = []
            status.error = str(exc)
        with self._lock:
            self._models = models
            status.installed = [m.name for m in models]
            self._status = status
        selections = {task: self._select(task, publish=True) for task in ("text", "vision")}
        with self._lock:
            status.selections = selections
            configured = self._configured()
            status.missing = [m for m in configured.values()
                              if m and not any(_matches(i, m) for i in status.installed)]
        self._publish_state()
        return status

    def _configured(self) -> dict[str, str]:
        s = self._settings()
        return {"text": getattr(s, "model", ""), "vision": getattr(s, "vision_model", "")}

    def _capabilities(self, name: str) -> tuple:
        if name not in self._caps:
            self._caps[name] = self.client.capabilities(name) if self._status.ollama_alive else ()
        return self._caps[name]

    def _is_vision(self, model: ModelInfo) -> bool:
        caps = self._capabilities(model.name)
        if caps:
            return "vision" in caps
        name = model.name.lower()
        families = " ".join(model.families).lower()
        return any(h in name for h in VISION_HINTS) or "clip" in families or "mllama" in families

    @staticmethod
    def _is_embedding(model: ModelInfo) -> bool:
        return any(h in model.name.lower() for h in EMBED_HINTS) or "bert" in model.family.lower()

    # ------------------------------------------------------------ seleção
    def _select(self, task: str, *, publish: bool) -> Selection:
        """Provedor escolhido pelo usuário (OpenAI, como no JARVIS original) quando permitido; senão o
        Ollama local. O motivo de não usar a OpenAI escolhida aparece na própria seleção."""
        openai = self._providers.get("openai")
        note = ""
        if openai is not None and getattr(openai, "chosen", lambda: False)():
            blocked = openai.blocked_reason() if hasattr(openai, "blocked_reason") else ""
            if not blocked and task in getattr(openai, "tasks", ("text",)):
                selection = Selection(task, f"openai:{openai.model}", True, "OpenAI (escolhida nas configurações)",
                                      provider="openai")
                if publish:
                    self._announce(task, selection)
                return selection
            note = f"OpenAI escolhida, mas {blocked or 'tarefa não suportada'}; usando o Ollama local"
        selection = self._select_ollama(task, publish=False)
        if note:
            selection.reason = f"{selection.reason} ({note})" if selection.reason else note
        if publish:
            self._announce(task, selection)
        return selection

    def _select_ollama(self, task: str, *, publish: bool) -> Selection:
        with self._lock:
            models = list(self._models)
            alive = self._status.ollama_alive
        configured = self._configured().get(task, "")
        default_hint = PREFERENCES.get(task, ("",))[0]
        hint = f"ollama pull {configured or default_hint}"
        if not alive:
            selection = Selection(task, None, False, "Ollama indisponível: inicie o Ollama para ativar o "
                                  "núcleo de inteligência local.", install_hint="ollama serve")
            selection = self._external_fallback(task, selection)
        else:
            chosen, reason = None, ""
            names = [m.name for m in models]
            if configured:
                exact = next((n for n in names if _matches(n, configured)), None)
                if exact:
                    chosen, reason = exact, "modelo configurado"
            if chosen is None:
                for preferred in PREFERENCES.get(task, ()):
                    match = next((n for n in names if _matches(n, preferred)), None)
                    if match:
                        chosen, reason = match, f"preferência ({preferred})"
                        break
            if chosen is None:
                candidates = [m for m in models if not self._is_embedding(m)]
                if task == "vision":
                    candidates = [m for m in candidates if self._is_vision(m)]
                else:
                    candidates.sort(key=lambda m: self._is_vision(m))   # texto: prefere não-visão
                if candidates:
                    chosen, reason = candidates[0].name, "único modelo compatível instalado"
            if chosen:
                if configured and not _matches(chosen, configured):
                    reason += f"; {configured} não está instalado"
                selection = Selection(task, chosen, True, reason)
            else:
                kind = "de visão" if task == "vision" else "de linguagem"
                selection = Selection(task, None, False,
                                      f"Nenhum modelo {kind} instalado no Ollama. Execute: {hint}",
                                      install_hint=hint)
                selection = self._external_fallback(task, selection)
        if publish:
            self._announce(task, selection)
        return selection

    def _external_fallback(self, task: str, selection: Selection) -> Selection:
        if not self._external_allowed():
            return selection
        for name, provider in self._providers.items():
            if name == "openai":
                continue                              # a OpenAI é escolha explícita, não plano B automático
            try:
                if provider.available() and task in getattr(provider, "tasks", ("text",)):
                    return Selection(task, getattr(provider, "model", name), True,
                                     f"provedor externo {name} (permitido pela configuração)", provider=name)
            except Exception:
                continue
        return selection

    def _external_allowed(self) -> bool:
        s = self._settings()
        if self._privacy is not None and not self._privacy.external_models_allowed():
            return False
        return bool(getattr(s, "allow_external_models", False)) and getattr(s, "privacy_mode", "local") != "local"

    def _announce(self, task: str, selection: Selection) -> None:
        with self._lock:
            previous = self._selected.get(task)
            self._selected[task] = selection.model
        if self._bus is None or previous == selection.model:
            return
        if selection.model is None:
            self._bus.publish(EventType.MODEL_UNAVAILABLE, selection.to_dict(), source="router")
            return
        kind = EventType.MODEL_CHANGED if previous else EventType.MODEL_SELECTED
        self._bus.publish(kind, {**selection.to_dict(), "previous": previous}, source="router")

    def _publish_state(self) -> None:
        if self._state is None:
            return
        with self._lock:
            payload = self._status.to_dict()
            text = self._selected.get("text") or ""
        self._state.update(_source="router", models=payload, active_model=text)

    def select(self, task: str = "text") -> Selection:
        self.refresh()
        return self._select(task, publish=True)

    def status(self) -> RouterStatus:
        with self._lock:
            return self._status

    # ------------------------------------------------------------ provedores externos (plugins)
    def register_provider(self, name: str, provider: Any) -> None:
        with self._lock:
            self._providers[name] = provider

    def unregister_provider(self, name: str) -> None:
        with self._lock:
            self._providers.pop(name, None)

    # ------------------------------------------------------------ chamada
    def chat(self, task: str, messages: list[dict], **kwargs: Any) -> ChatResult:
        selection = self.select(task)
        if not selection.available or not selection.model:
            raise ModelUnavailable(selection)
        if selection.provider == "openai":
            from .openai_provider import ProviderError
            try:
                return self._providers["openai"].chat(messages, **kwargs)
            except ProviderError as exc:
                if exc.kind == "CANCELLED":
                    raise
                log.warning("OpenAI falhou (%s); usando o Ollama local nesta chamada", exc.kind)
                if self._bus is not None:
                    self._bus.publish(EventType.MODEL_UNAVAILABLE, {"task": task, "provider": "openai",
                                                                    "kind": exc.kind, "reason": str(exc),
                                                                    "fallback": "ollama"}, source="router")
                selection = self._select_ollama(task, publish=False)
                if not selection.available or not selection.model or selection.provider != "ollama":
                    raise ModelUnavailable(Selection(task, None, False, f"OpenAI: {exc}; e o Ollama local também "
                                                     f"está indisponível ({selection.reason})")) from exc
        if selection.provider != "ollama":
            provider = self._providers[selection.provider]
            return provider.chat(messages, **kwargs)
        try:
            return self.client.chat(selection.model, messages, **kwargs)
        except OllamaError as exc:
            if exc.kind != "MODEL_MISSING":
                raise
            self.refresh(force=True)                 # o modelo pode ter sido removido
            retry = self._select_ollama(task, publish=True)
            if not retry.available or not retry.model or retry.model == selection.model:
                raise ModelUnavailable(retry) from exc
            return self.client.chat(retry.model, messages, **kwargs)
