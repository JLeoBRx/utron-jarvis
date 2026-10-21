"""Protocolo de tarefas da TARDIS (``TaskEnvelope``).

Campos: ``id``, ``kind``, ``input``, ``origin`` (jarvis, usuario, tardis, agendador), ``chain`` (os
saltos até aqui), ``state`` (QUEUED → RUNNING → DONE | FAILED | REJECTED | CANCELLED), ``result``
(resumo, itens, fontes, ações propostas), ``error`` (código e mensagem), ``created``/``started``/
``finished``, ``duration_ms``, ``log`` (operações relevantes) e ``model`` (o modelo usado ou "sem modelo").

Regras que este módulo garante:

* cadeia de no máximo 2 saltos (ex.: JARVIS → TARDIS → sub-análise) e nenhum salto repetido — impede
  ciclos de delegação; a TARDIS nunca devolve uma tarefa ao JARVIS;
* prazo por tipo de análise; cancelamento a qualquer momento;
* sem dado suficiente → FAILED com o motivo (nunca um resultado inventado).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

STATES = ("QUEUED", "RUNNING", "DONE", "FAILED", "REJECTED", "CANCELLED")
FINAL = frozenset({"DONE", "FAILED", "REJECTED", "CANCELLED"})
ORIGINS = ("jarvis", "usuario", "tardis", "agendador")
MAX_HOPS = 2
STATE_LABELS = {"QUEUED": "na fila", "RUNNING": "em execução", "DONE": "concluída", "FAILED": "falhou",
                "REJECTED": "recusada", "CANCELLED": "cancelada"}


@dataclass(frozen=True)
class KindSpec:
    key: str
    label: str
    deadline: float                     # segundos
    panel: str                          # painel do console na sala de controle


KINDS: dict[str, KindSpec] = {spec.key: spec for spec in (
    KindSpec("consulta", "consulta contextual", 60.0, "analise"),
    KindSpec("planejamento", "planejamento", 120.0, "planejamento"),
    KindSpec("organizacao", "organização", 20.0, "arquivo"),
    KindSpec("rotinas", "rotinas", 10.0, "rotinas"),
    KindSpec("telemetria", "telemetria do Noctário", 20.0, "telemetria"),
    KindSpec("diagnostico", "diagnóstico", 30.0, "diagnostico"),
    KindSpec("coordenacao", "coordenação de módulos", 5.0, "diagnostico"),
    KindSpec("projeto", "memória de projeto", 10.0, "analise"),
)}
PANELS = ("analise", "planejamento", "arquivo", "rotinas", "telemetria", "diagnostico")
PANEL_LABELS = {"analise": "ANÁLISE", "planejamento": "PLANEJAMENTO", "arquivo": "ARQUIVO", "rotinas": "ROTINAS",
                "telemetria": "TELEMETRIA", "diagnostico": "DIAGNÓSTICO"}


class TaskFailed(Exception):
    """Falha honesta de um analisador: ``code`` (NO_DATA, NO_MODEL, INVALID_INPUT, ...) e a mensagem."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TaskCancelled(Exception):
    pass


@dataclass
class ProposedAction:
    """Ação que a TARDIS PROPÕE. Só o JARVIS executa, com a confirmação do usuário."""

    description: str
    skill: str
    args: dict = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    summary: str
    items: list = field(default_factory=list)          # [{"title", "detail", "source", "severity"?}]
    sources: list = field(default_factory=list)        # de onde veio cada informação
    actions: list = field(default_factory=list)        # [ProposedAction]
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "items": list(self.items), "sources": list(self.sources),
                "actions": [a.to_dict() if isinstance(a, ProposedAction) else dict(a) for a in self.actions],
                "data": dict(self.data)}


@dataclass
class TaskEnvelope:
    kind: str
    input: dict
    origin: str
    chain: list = field(default_factory=list)
    id: str = field(default_factory=lambda: "t" + uuid.uuid4().hex[:11])
    state: str = "QUEUED"
    result: TaskResult | None = None
    error: dict | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    duration_ms: int | None = None
    log: list = field(default_factory=list)
    model: str = ""

    @property
    def hop(self) -> str:
        return f"tardis:{self.kind}"

    @property
    def final(self) -> bool:
        return self.state in FINAL

    @property
    def label(self) -> str:
        spec = KINDS.get(self.kind)
        return spec.label if spec else self.kind

    def note(self, text: str) -> None:
        self.log.append(f"{time.strftime('%H:%M:%S')} {text}")
        del self.log[:-40]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "kind_label": self.label, "input": dict(self.input),
                "origin": self.origin, "chain": list(self.chain), "state": self.state,
                "state_label": STATE_LABELS.get(self.state, self.state),
                "result": self.result.to_dict() if self.result else None, "error": self.error,
                "created": self.created, "started": self.started, "finished": self.finished,
                "duration_ms": self.duration_ms, "log": list(self.log), "model": self.model}

    @classmethod
    def from_dict(cls, data: dict) -> "TaskEnvelope":
        result = data.get("result")
        envelope = cls(kind=data["kind"], input=dict(data.get("input") or {}), origin=data.get("origin", "usuario"),
                       chain=list(data.get("chain") or []), id=data["id"], state=data.get("state", "QUEUED"),
                       error=data.get("error"), created=data.get("created") or time.time(),
                       started=data.get("started"), finished=data.get("finished"),
                       duration_ms=data.get("duration_ms"), log=list(data.get("log") or []),
                       model=data.get("model") or "")
        if result:
            envelope.result = TaskResult(result.get("summary", ""), list(result.get("items") or []),
                                         list(result.get("sources") or []),
                                         [ProposedAction(**a) for a in result.get("actions") or []],
                                         dict(result.get("data") or {}))
        return envelope


def check_chain(kind: str, origin: str, chain: list[str]) -> str:
    """'' se a tarefa pode entrar; senão, o motivo da recusa (ciclo, saltos demais, origem inválida)."""
    if kind not in KINDS:
        return f"tipo de análise desconhecido: {kind}"
    if origin not in ORIGINS:
        return f"origem desconhecida: {origin}"
    hops = list(chain or [])
    if len(hops) > MAX_HOPS:
        return f"cadeia de delegação longa demais ({' → '.join(hops)}): no máximo {MAX_HOPS} saltos"
    hop = f"tardis:{kind}"
    if hop in hops:
        return f"ciclo de delegação: {hop} já está na cadeia ({' → '.join(hops)})"
    if origin == "tardis" and not any(h.startswith("tardis:") for h in hops):
        return "sub-análise da TARDIS sem a análise que a pediu na cadeia"
    if "jarvis" in hops[1:]:
        return "a TARDIS não devolve tarefas ao JARVIS"
    return ""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
