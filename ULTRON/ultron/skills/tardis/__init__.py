"""Skills da TARDIS — a ponte JARVIS → TARDIS.

* ``tardis.consult``: o JARVIS envia uma tarefa à TARDIS (origem "jarvis", cadeia ["jarvis"]) e espera o
  resultado. A resposta diz qual análise rodou, qual modelo usou (o MESMO do JARVIS, ou "sem modelo") e de
  onde veio cada informação. Ações propostas NÃO são executadas aqui: o núcleo as oferece ao usuário como
  sugestão, que só roda com "sim" e passa pelo executor (permissões, risco, verificação).
* ``tardis.note``: grava uma nota, decisão ou parâmetro na memória de projeto (categoria "arquivos").
"""
from __future__ import annotations

from ...tardis.protocol import KINDS
from ...tardis.store import NOTE_KINDS
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

WAIT_MARGIN = 20.0           # espera além do prazo do tipo (fila + tolerância), abaixo do timeout da skill


def _engine(ctx):
    extras = ctx.extras or {}
    engine = extras.get("tardis")
    if engine is None:
        engine = getattr(extras.get("core"), "tardis", None)
    return engine


def _registry(ctx):
    return (ctx.extras or {}).get("registry")


class Consult(Skill):
    name = "tardis.consult"
    description = ("Consultar a TARDIS, o segundo cérebro do JARVIS: consulta contextual na memória (kind consulta, "
                   "com question), planejamento de um objetivo (planejamento, com goal), organização da memória "
                   "pessoal (organizacao), rotinas e lembretes (rotinas), telemetria do Noctário (telemetria), "
                   "diagnóstico do sistema (diagnostico), estado dos módulos (coordenacao) ou memória de projeto "
                   "(projeto). Devolve o resultado com as fontes; não executa ações.")
    category = "assistant"
    inputs = schema({"kind": string(20, enum=sorted(KINDS)), "question": string(400), "goal": string(400),
                     "project": string(80), "search": string(120)}, ("kind",))
    risk = Risk.NONE
    timeout = max(spec.deadline for spec in KINDS.values()) + WAIT_MARGIN + 15.0

    def describe_action(self, args):
        spec = KINDS.get(args.get("kind", ""))
        subject = args.get("question") or args.get("goal") or args.get("project") or ""
        return f"consultar a TARDIS ({spec.label if spec else args.get('kind')})" + (f": {subject[:80]}" if subject
                                                                                   else "")

    def execute(self, ctx, kind: str, question: str = "", goal: str = "", project: str = "",
                search: str = "") -> SkillResult:
        engine = _engine(ctx)
        if engine is None:
            return SkillResult(False, error="a TARDIS não está disponível nesta execução", error_kind="UNAVAILABLE")
        data = {k: v for k, v in {"question": question, "goal": goal, "project": project, "search": search}.items()
                if v}
        if kind == "consulta" and not question:
            return SkillResult(False, error="faltou a pergunta para a TARDIS", error_kind="INVALID_ARGUMENT")
        if kind == "planejamento" and not goal:
            return SkillResult(False, error="faltou o objetivo a planejar", error_kind="INVALID_ARGUMENT")
        task = engine.request(kind, data, origin="jarvis", chain=["jarvis"],
                              timeout=KINDS[kind].deadline + WAIT_MARGIN, cancel=ctx.cancel)
        if task.state != "DONE" or task.result is None:
            error = task.error or {}
            code = str(error.get("code") or task.state)
            kind_of_error = "CANCELLED" if task.state == "CANCELLED" else f"TARDIS_{code}"
            return SkillResult(False, error=f"TARDIS ({task.label}): {error.get('message') or task.state.lower()}",
                               error_kind=kind_of_error, data={"task": task.id, "state": task.state, "code": code})
        result = task.result
        text = f"TARDIS — {task.label} ({task.model or 'sem modelo'}): {result.summary}"
        if result.sources:
            text += f" Fontes: {', '.join(result.sources[:4])}."
        registry = _registry(ctx)
        offered = [a for a in result.actions if registry is None or a.skill in registry]
        if offered:
            text += (f" A TARDIS propõe: {offered[0].description}. Diga “sim” para eu executar ou “não” para "
                     f"descartar.")
        return SkillResult(True, text, [f"tarefa {task.id} concluída", f"modelo: {task.model or 'sem modelo'}"]
                           + list(result.sources[:3]),
                           {"task": task.id, "kind": kind, "summary": result.summary, "items": list(result.items[:12]),
                            "sources": list(result.sources), "model": task.model,
                            "actions": [a.to_dict() for a in offered]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        engine = _engine(ctx)
        stored = engine.store.get(result.data["task"]) if engine is not None else None
        ok = stored is not None and stored.state == "DONE"
        return VerificationResult.from_checks([check("stored", ok, "resultado gravado e relido do banco" if ok else
                                                     "a tarefa não foi encontrada concluída no banco")])


class Note(Skill):
    name = "tardis.note"
    description = ("Gravar na memória de projeto da TARDIS uma nota, uma decisão ou um parâmetro (ex.: 'decisão: "
                   "usar Kd 0,12 no Noctário'). Nunca senhas, tokens ou dados sensíveis.")
    category = "memory"
    inputs = schema({"text": string(600), "project": string(80), "kind": string(12, enum=list(NOTE_KINDS))},
                    ("text",))
    risk = Risk.LOW
    permission = "arquivos"

    def describe_action(self, args):
        return f"gravar na memória de projeto ({args.get('kind', 'nota')}): {args.get('text', '')[:80]}"

    def execute(self, ctx, text: str, project: str = "", kind: str = "nota") -> SkillResult:
        engine = _engine(ctx)
        if engine is None:
            return SkillResult(False, error="a TARDIS não está disponível nesta execução", error_kind="UNAVAILABLE")
        try:
            note_id = engine.add_note(text, project=project, kind=kind, source="jarvis")
        except ValueError as exc:
            return SkillResult(False, error=str(exc), error_kind="INVALID_ARGUMENT")
        label = {"nota": "Nota", "decisao": "Decisão", "parametro": "Parâmetro"}[kind]
        scope = f" do projeto {project}" if project else ""
        return SkillResult(True, f"{label} gravada na memória de projeto{scope} da TARDIS.", [f"nota #{note_id}"],
                           {"id": note_id, "project": project, "kind": kind})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        engine = _engine(ctx)
        notes = engine.store.notes(project=result.data["project"] or None, limit=20) if engine is not None else []
        ok = any(n["id"] == result.data["id"] for n in notes)
        return VerificationResult.from_checks([check("persisted", ok, "nota relida do banco" if ok else
                                                     "a nota não foi encontrada após gravar")])


SKILLS = (Consult, Note)
