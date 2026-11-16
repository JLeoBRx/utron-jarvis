"""Dynamic Model Router.

Consulta o Ollama (``/api/tags`` e ``/api/show``) para saber quais modelos existem de fato
e escolhe um por tarefa:

* ``text``   — preferência ``qwen2.5:3b``;
* ``vision`` — preferência ``qwen2.5vl:3b``.

Nunca presume disponibilidade: se nenhum modelo adequado existir, a seleção vem marcada
como indisponível, com a instrução exata para instalar. Provedores externos (plugins)
só são considerados quando o modo de privacidade permite.

Fase D (Phoenix): ``chat`` decide POR TAREFA com o perfil de inteligência (``profiles.py``): modelo local
rápido ou robusto, ou nuvem rápida/robusta. Antes do PRIMEIRO uso pago pede autorização ao usuário; respeita o
limite mensal (``usage.py``); nunca manda memória pessoal, tela ou imagens à nuvem sem a opção explícita; e
nunca troca de provedor em silêncio — a rota (com o motivo e os avisos) acompanha o resultado e vira a
procedência da resposta.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from . import profiles
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


def _params(text: str) -> float:
    """"7.6B" → 7.6 · "500M" → 0.5 · "" → 0 (bilhões de parâmetros)."""
    text = str(text or "").strip().upper()
    try:
        if text.endswith("B"):
            return float(text[:-1])
        if text.endswith("M"):
            return float(text[:-1]) / 1000.0
    except ValueError:
        return 0.0
    return 0.0


def _size(model: ModelInfo | None) -> float:
    if model is None:
        return 0.0
    return _params(model.parameter_size) or model.size_bytes / 1e9


def _strip_private(messages: list[dict], *, share_memory: bool) -> list[dict]:
    """Mensagens sem as marcas internas (``cloud_content``, ``history``); para a nuvem (``share_memory`` falso),
    o prompt de sistema troca a versão completa (memória pessoal, tela, preferências) pela versão sem dados
    pessoais e o histórico da conversa fica de fora."""
    out = []
    for msg in messages:
        if msg.get("history") and not share_memory:
            continue                                   # histórico da conversa: só com a opção ligada
        if "cloud_content" not in msg and "history" not in msg:
            out.append(msg)
            continue
        clean = {k: v for k, v in msg.items() if k not in ("cloud_content", "history")}
        if not share_memory and "cloud_content" in msg:
            clean["content"] = msg["cloud_content"]
        out.append(clean)
    return out


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
                 bus=None, state=None, privacy=None, cache_seconds: float = 30.0, usage=None,
                 consent: Callable[[str], bool] | None = None):
        self.client = client
        self.usage = usage                     # UsageLedger (mesmo banco) — None só em testes isolados
        self._consent = consent                # pergunta ao usuário antes do primeiro uso pago
        self._thread = threading.local()       # a rota da última chamada nesta thread (procedência)
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

    # ------------------------------------------------------------ roteamento por tarefa (Fase D)
    def robust_local(self) -> str | None:
        """O modelo local para tarefas pesadas: ``model_robust`` se instalado; senão o maior modelo de texto
        instalado que seja claramente maior que o rápido. Nenhum → None (a rota diz o que instalar)."""
        with self._lock:
            models = list(self._models)
            alive = self._status.ollama_alive
        if not alive:
            return None
        configured = str(getattr(self._settings(), "model_robust", "") or "")
        names = [m.name for m in models]
        if configured:
            return next((n for n in names if _matches(n, configured)), None)
        fast = self._select_ollama("text", publish=False).model
        fast_info = next((m for m in models if m.name == fast), None)
        base = _size(fast_info)
        bigger = [m for m in models if m.name != fast and not self._is_embedding(m) and not self._is_vision(m)
                  and _size(m) > max(base * 1.4, 0.0) and _size(m) > 0]
        return max(bigger, key=_size).name if bigger else None

    def availability(self, task: str = "text") -> profiles.Availability:
        s = self._settings()
        fast = self._select_ollama(task, publish=False)
        local_fast = bool(fast.available and fast.model and fast.provider == "ollama")
        local_robust = bool(task == "text" and self.robust_local())
        provider = self._providers.get("openai")
        if provider is None:
            cloud_ready, blocked = False, "OpenAI não configurada"
        else:
            blocked = provider.cloud_blocked_reason() if hasattr(provider, "cloud_blocked_reason") else \
                provider.blocked_reason()
            if not blocked and self._privacy is not None and not self._privacy.external_models_allowed():
                blocked = "a política de privacidade não permite modelos externos"
            cloud_ready = not blocked
        within, why = True, ""
        if self.usage is not None:
            within, why, _month = self.usage.budget()
        return profiles.Availability(local_fast, local_robust, cloud_ready, blocked, within, why,
                                     bool(getattr(s, "cloud_images", False)),
                                     bool(getattr(s, "cloud_share_memory", False)))

    def route(self, task: str, messages: list[dict], *, purpose: str = "", query: str = "",
              tools: bool = False) -> profiles.Route:
        purpose = purpose or ("visao" if task == "vision" else "conversa")
        if not query:
            query = next((str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"), "")
        images = any(m.get("images") for m in messages)
        tools = tools or any(m.get("role") == "tool" for m in messages)     # resultados de ferramentas locais
        chars = sum(len(str(m.get("content") or "")) for m in messages)
        assessment = profiles.assess(query, purpose=purpose, images=images, tools=tools, context_chars=chars)
        profile = profiles.effective_profile(self._settings())
        return profiles.decide(assessment, profile, self.availability(task))

    def reset_route(self) -> None:
        self._thread.route = None

    def last_route(self) -> dict:
        """A rota da última chamada feita NESTA thread (o orquestrador usa para a procedência)."""
        return dict(getattr(self._thread, "route", None) or {})

    def _remember(self, route: profiles.Route, *, model: str, provider: str, web: bool = False) -> dict:
        info = {**route.to_dict(), "model": model, "provider": provider, "web": bool(web)}
        self._thread.route = info
        return info

    def _record(self, route: profiles.Route, *, provider: str, model: str, result: ChatResult | None,
                seconds: float, ok: bool, detail: str = "") -> None:
        if self.usage is None:
            return
        self.usage.record(provider=provider, model=model, purpose=route.assessment.purpose if route.assessment
                          else "", target=route.target,
                          input_tokens=getattr(result, "input_tokens", 0) if result else 0,
                          output_tokens=getattr(result, "eval_count", 0) if result else 0,
                          seconds=seconds, ok=ok, detail=detail)

    def _consented(self, route: profiles.Route, model: str) -> bool:
        """Primeiro uso pago: pergunta ao usuário (uma vez). Sem como perguntar, não usa."""
        if float(getattr(self._settings(), "cloud_consent_at", 0.0) or 0.0) > 0:
            return True
        if self._consent is None:
            route.notes.append("uso pago da nuvem ainda não autorizado")
            return False
        description = (f"Usar a OpenAI (serviço PAGO) pela primeira vez: modelo {model}, perfil "
                       f"{profiles.PROFILE_LABELS.get(route.profile, route.profile)}. O consumo fica registrado e "
                       f"limitado em CONFIGURAÇÕES > INTELIGÊNCIA; memória pessoal e tela não são enviadas.")
        try:
            allowed = bool(self._consent(description))
        except Exception:
            log.warning("pedido de autorização do uso pago falhou", exc_info=True)
            allowed = False
        if not allowed:
            route.notes.append("uso pago da nuvem não autorizado")
        return allowed

    # ------------------------------------------------------------ chamada
    def chat(self, task: str, messages: list[dict], *, purpose: str = "", query: str = "",
             **kwargs: Any) -> ChatResult:
        self.refresh()
        route = self.route(task, messages, purpose=purpose, query=query, tools=bool(kwargs.get("tools")))
        if route.cloud:
            result = self._chat_cloud(task, route, messages, kwargs)
            if result is not None:
                return result
            local = profiles.decide(route.assessment, "local", self.availability(task)) if route.assessment \
                else route
            local.notes = route.notes + local.notes
            local.profile = route.profile
            local.reason = f"{route.reason} → {local.reason}"
            route = local
        return self._chat_local(task, route, messages, kwargs)

    def _chat_cloud(self, task: str, route: profiles.Route, messages: list[dict], kwargs: dict) -> ChatResult | None:
        from .openai_provider import ProviderError
        provider = self._providers.get("openai")
        if provider is None:
            route.notes.append("OpenAI não configurada")
            return None
        model = provider.model_for(route.target) if hasattr(provider, "model_for") else provider.model
        if not self._consented(route, model):
            return None
        share = bool(getattr(self._settings(), "cloud_share_memory", False))
        started = time.perf_counter()
        try:
            result = provider.chat(_strip_private(messages, share_memory=share), model=model, **kwargs)
        except ProviderError as exc:
            if exc.kind == "CANCELLED":
                raise
            self._record(route, provider="openai", model=model, result=None,
                         seconds=time.perf_counter() - started, ok=False, detail=exc.kind)
            log.warning("OpenAI falhou (%s); usando o Ollama local nesta chamada", exc.kind)
            route.notes.append(f"a nuvem falhou ({exc.kind}); respondido pelo modelo local")
            if self._bus is not None:
                self._bus.publish(EventType.MODEL_UNAVAILABLE, {"task": task, "provider": "openai",
                                                                "kind": exc.kind, "reason": str(exc),
                                                                "fallback": "ollama"}, source="router")
            return None
        self._record(route, provider="openai", model=model, result=result, seconds=time.perf_counter() - started,
                     ok=True)
        result.route = self._remember(route, model=f"openai:{model}", provider="openai", web=result.web)
        return result

    def _chat_local(self, task: str, route: profiles.Route, messages: list[dict], kwargs: dict) -> ChatResult:
        messages = _strip_private(messages, share_memory=True)
        selection = self._select_ollama(task, publish=True)
        if route.target == profiles.LOCAL_ROBUST:
            robust = self.robust_local()
            if robust:
                selection = Selection(task, robust, True, "modelo local robusto")
        if not selection.available or not selection.model:
            notes = "; ".join(route.notes)
            raise ModelUnavailable(Selection(task, None, False, selection.reason + (f" ({notes})" if notes else ""),
                                             install_hint=selection.install_hint))
        if selection.provider != "ollama":              # plugin externo permitido (Ollama fora do ar)
            provider = self._providers[selection.provider]
            result = provider.chat(messages, **kwargs)
            result.route = self._remember(route, model=str(selection.model), provider=selection.provider)
            return result
        started = time.perf_counter()
        try:
            result = self.client.chat(selection.model, messages, **kwargs)
        except OllamaError as exc:
            self._record(route, provider="ollama", model=selection.model, result=None,
                         seconds=time.perf_counter() - started, ok=False, detail=exc.kind)
            if exc.kind in ("UNAVAILABLE", "TIMEOUT", "HTTP", "BAD_RESPONSE") and self._bus is not None:
                # o modelo falhou no meio do pedido: o rosto e o histórico mostram a falha real
                self._bus.publish(EventType.MODEL_UNAVAILABLE, {"task": task, "provider": "ollama",
                                                                "model": selection.model, "kind": exc.kind,
                                                                "reason": str(exc)[:200]}, source="router")
            if exc.kind != "MODEL_MISSING":
                raise
            self.refresh(force=True)                 # o modelo pode ter sido removido
            retry = self._select_ollama(task, publish=True)
            if not retry.available or not retry.model or retry.model == selection.model:
                raise ModelUnavailable(retry) from exc
            selection = retry
            started = time.perf_counter()
            result = self.client.chat(retry.model, messages, **kwargs)
        self._record(route, provider="ollama", model=selection.model, result=result,
                     seconds=time.perf_counter() - started, ok=True)
        result.route = self._remember(route, model=str(selection.model), provider="ollama")
        return result
