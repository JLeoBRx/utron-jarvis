"""Analisadores da TARDIS. Cada um recebe um ``Run`` (a tarefa, o contexto, o prazo e o cancelamento)
e devolve um ``TaskResult`` — ou levanta ``TaskFailed`` com o motivo quando não há dado suficiente.

O que um analisador PODE usar está em ``TardisContext``: leitura do Segundo Cérebro, da memória, do
histórico de atividades, da saúde, da voz, dos modelos, do Noctário e da memória de projeto. Nenhum
analisador executa skills: ações viram ``ProposedAction`` (o JARVIS executa só com confirmação).
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from ..protocol import KINDS, TaskCancelled, TaskEnvelope, TaskFailed

DETERMINISTIC = "sem modelo: análise determinística"
STOPWORDS = {"sobre", "como", "quando", "onde", "qual", "quais", "quem", "para", "pela", "pelo", "esta", "este",
             "isso", "isto", "essa", "esse", "minha", "minhas", "meus", "meu", "tenho", "temos", "fazer", "favor",
             "tardis", "jarvis", "consulte", "consultar", "pergunte", "perguntar", "voce", "voces", "existe", "algum",
             "alguma", "mais", "menos", "muito", "sobre", "entre", "depois", "antes", "ainda", "tudo", "todos",
             "todas", "nosso", "nossa", "dele", "dela", "aquele", "aquela", "estou", "estao", "seria", "pode"}


@dataclass
class TardisContext:
    """O que os analisadores podem LER (nada aqui executa ações)."""

    second_brain: Any = None
    memory: Any = None
    activity: Any = None
    health: Any = None
    router: Any = None
    voice_probe: Callable[[], dict] | None = None
    state: Any = None
    lifecycle: Any = None
    runtime: Any = None
    registry: Any = None
    store: Any = None
    engine: Any = None
    noctario: Any = None
    noctario_runs: Callable[[int], list] | None = None
    extras: dict = field(default_factory=dict)

    def has_skill(self, name: str) -> bool:
        return bool(self.registry is not None and name in self.registry)


class Run:
    """Uma execução: prazo, cancelamento, registro de operações e acesso ao MESMO modelo do JARVIS."""

    def __init__(self, envelope: TaskEnvelope, ctx: TardisContext, deadline: float,
                 cancelled: threading.Event | None = None):
        self.envelope = envelope
        self.ctx = ctx
        self.deadline = deadline
        self._cancelled = cancelled or threading.Event()
        self.model_reason = ""
        self.related_activity: set[str] = set()      # registros do próprio pedido (nunca usados como fonte)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check(self) -> None:
        if self._cancelled.is_set():
            raise TaskCancelled("cancelada")
        if time.monotonic() > self.deadline:
            spec = KINDS.get(self.envelope.kind)
            limit = f" de {spec.deadline:g} s" if spec else ""
            raise TaskFailed("TIMEOUT", f"{self.envelope.label} excedeu o prazo{limit}")

    def note(self, text: str) -> None:
        self.envelope.note(text)

    def language(self, system: str, prompt: str, *, fmt: str | None = None) -> tuple[str | None, str]:
        """(texto, rótulo do modelo) usando o MESMO modelo do JARVIS; (None, motivo) se não houver modelo."""
        router = self.ctx.router
        if router is None:
            return None, "roteador de modelos indisponível"
        self.check()
        timeout = max(5.0, min(90.0, self.remaining() - 1.0))
        try:
            result = router.chat("text", [{"role": "system", "content": system},
                                          {"role": "user", "content": prompt}],
                                 fmt=fmt, timeout=timeout, cancel=self)
        except Exception as exc:                        # modelo ausente, Ollama fora, OpenAI recusada...
            reason = str(exc).split("\n")[0][:160] or type(exc).__name__
            self.note(f"modelo indisponível: {reason}")
            return None, reason
        text = str(getattr(result, "content", "") or "").strip()
        if not text:
            return None, "o modelo não devolveu texto"
        model = str(getattr(result, "model", "") or "modelo")
        self.note(f"linguagem: {model}")
        return text, f"{model} (o mesmo do JARVIS)"


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def keywords(text: str, limit: int = 4) -> list[str]:
    words = [w for w in normalize(text).split() if len(w) >= 4 and w not in STOPWORDS]
    seen: list[str] = []
    for word in sorted(words, key=len, reverse=True):
        if word not in seen:
            seen.append(word)
    return seen[:limit]


def clean_input(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def registry() -> dict[str, Callable[[Run, dict], Any]]:
    from .context import consulta, projeto
    from .diagnostics import coordenacao, diagnostico
    from .organization import organizacao, rotinas
    from .planning import planejamento
    from .telemetry import telemetria
    return {"consulta": consulta, "planejamento": planejamento, "organizacao": organizacao, "rotinas": rotinas,
            "telemetria": telemetria, "diagnostico": diagnostico, "coordenacao": coordenacao, "projeto": projeto}
