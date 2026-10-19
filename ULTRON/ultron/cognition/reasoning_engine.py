"""REASONING ENGINE — usa o modelo local para responder, planejar e agir com ferramentas.

* Nunca expõe raciocínio interno: a interface recebe apenas fases (ANALYZING, EVALUATING...).
* Respostas passam pelo estilo da personalidade.
* No modo agêntico, cada chamada de ferramenta é executada e VERIFICADA pelo núcleo; o
  modelo recebe a evidência e não pode declarar sucesso sem ela.
* Sem modelo disponível, levanta ``ModelUnavailable`` — nunca inventa resposta.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..personality import stylize
from .context_engine import CognitiveContext, ContextEngine

log = logging.getLogger("ultron.reasoning")

AGENT_RULES = (
    "Para agir no computador use SOMENTE as ferramentas fornecidas, uma de cada vez. Aguarde o resultado e a "
    "verificação antes do próximo passo. Se uma ferramenta falhar ou não for verificada, diga isso; nunca afirme "
    "sucesso sem verificação. Ações sensíveis serão submetidas à autorização do usuário automaticamente. "
    "Se o pedido for apenas uma pergunta ou conversa, responda diretamente sem ferramentas. Resposta final: curta."
)
PLAN_PROMPT = (
    "Você é o planejador do JARVIS. Decomponha o objetivo em passos executáveis usando SOMENTE as skills listadas. "
    "Responda SOMENTE com JSON no formato {\"steps\": [{\"description\": \"...\", \"skill\": \"nome\", "
    "\"args\": {}}], \"confidence\": 0.0}. No máximo 8 passos. Argumentos devem seguir os nomes da lista. "
    "Se o objetivo não exigir ações, devolva steps vazio."
)


@dataclass
class AgenticOutcome:
    answer: str
    calls: list = field(default_factory=list)
    steps: int = 0
    stopped: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "calls": self.calls, "steps": self.steps, "stopped": self.stopped}


def _parse_json(text: str) -> dict | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else None
            except ValueError:
                return None
    return None


class ReasoningEngine:
    def __init__(self, router, context: ContextEngine, *, settings_getter: Callable[[], Any], state=None):
        self.router = router
        self.context = context
        self._settings = settings_getter
        self._state = state

    def _phase(self, phase: str) -> None:
        if self._state is not None:
            self._state.set_cognitive_phase(phase, source="reasoning")

    def _options(self, **extra: Any) -> dict:
        s = self._settings()
        options = {"temperature": float(getattr(s, "llm_temperature", 0.4))}
        options.update(extra)
        return options

    # ------------------------------------------------------------ conversa
    def respond(self, text: str, ctx: CognitiveContext, *, cancel=None,
                on_token: Callable[[str], None] | None = None) -> str:
        self._phase("EVALUATING")
        messages = self.context.messages(ctx, text, extra_system="Responda de forma curta e precisa.")
        result = self.router.chat("text", messages, options=self._options(num_predict=420),
                                  timeout=getattr(self._settings(), "llm_timeout", 120.0), cancel=cancel,
                                  on_token=on_token)
        return stylize(result.content) or "Sem resposta do modelo."

    # ------------------------------------------------------------ plano explícito
    def plan(self, goal: str, ctx: CognitiveContext, catalog: str, *, cancel=None) -> dict | None:
        self._phase("PLANNING")
        system = self.context.system_prompt(ctx, PLAN_PROMPT + "\nSkills disponíveis:\n" + catalog)
        result = self.router.chat("text", [{"role": "system", "content": system},
                                           {"role": "user", "content": f"Objetivo: {goal}"}],
                                  fmt="json", options=self._options(temperature=0.1, num_predict=600),
                                  timeout=getattr(self._settings(), "llm_timeout", 120.0), cancel=cancel)
        data = _parse_json(result.content)
        if not data or not isinstance(data.get("steps"), list):
            return None
        return data

    # ------------------------------------------------------------ agente com ferramentas
    def agentic(self, goal: str, ctx: CognitiveContext, *, tools: list[dict],
                call_tool: Callable[[str, dict], dict], cancel=None) -> AgenticOutcome:
        s = self._settings()
        max_steps = int(getattr(s, "max_agent_steps", 8))
        max_calls = int(getattr(s, "max_tool_calls", 10))
        messages = self.context.messages(ctx, goal, extra_system=AGENT_RULES)
        outcome = AgenticOutcome("")
        for step in range(max_steps):
            if cancel is not None and getattr(cancel, "cancelled", False):
                outcome.stopped = "cancelado"
                break
            self._phase("EVALUATING" if step == 0 else "SELECTING")
            result = self.router.chat("text", messages, tools=tools, options=self._options(num_predict=500),
                                      timeout=getattr(s, "llm_timeout", 120.0), cancel=cancel)
            outcome.steps = step + 1
            if not result.tool_calls:
                outcome.answer = stylize(result.content)
                return outcome
            messages.append(result.message())
            for call in result.tool_calls:
                if len(outcome.calls) >= max_calls:
                    messages.append({"role": "tool", "content": json.dumps(
                        {"erro": "limite de ferramentas atingido; nenhuma outra ação foi executada"})})
                    outcome.stopped = "limite de ferramentas"
                    break
                function = call.get("function") or {}
                name = str(function.get("name") or "")
                args = function.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                observation = call_tool(name, args if isinstance(args, dict) else {})
                outcome.calls.append({"skill": name, "args": args, "observation": observation})
                messages.append({"role": "tool", "content": json.dumps(observation, ensure_ascii=False, default=str)})
                if observation.get("stop"):
                    outcome.stopped = observation.get("stop")
                    break
            if outcome.stopped:
                break
        if not outcome.answer:
            outcome.answer = ("Interrompido: " + outcome.stopped + ".") if outcome.stopped else \
                "Não concluí dentro do limite seguro de etapas."
        return outcome
