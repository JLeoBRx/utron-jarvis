"""Skills de memória: lembrar, recordar, esquecer e preferências."""
from __future__ import annotations

from ...memory.preference_memory import ALLOWED
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string


class Remember(Skill):
    name = "memory.remember"
    description = "Guardar um fato informado pelo usuário (nunca senhas ou dados financeiros)."
    category = "memory"
    inputs = schema({"subject": string(80), "fact": string(600)}, ("subject", "fact"))
    risk = Risk.LOW

    def execute(self, ctx, subject: str, fact: str) -> SkillResult:
        try:
            stored = ctx.memory.remember_fact(subject, fact)
        except ValueError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        return SkillResult(True, f"Registrado: {stored}.", ["memória semântica"], {"subject": stored})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        fact = ctx.memory.semantic.get(result.data["subject"])
        ok = fact is not None and fact.fact == " ".join(args["fact"].split())
        return VerificationResult.from_checks([check("persisted", ok, "fato lido de volta da base")])


class Recall(Skill):
    name = "memory.recall"
    description = "Consultar a memória (fatos, experiências, procedimentos e conceitos)."
    category = "memory"
    inputs = schema({"query": string(200)}, ("query",))
    risk = Risk.NONE

    def execute(self, ctx, query: str) -> SkillResult:
        results = ctx.memory.recall(query, limit=6)
        if not results:
            return SkillResult(True, "Nenhuma memória relacionada.", [], {"results": []})
        return SkillResult(True, "Memórias: " + " | ".join(r.text for r in results), [f"{len(results)} item(ns)"],
                           {"results": [r.to_dict() for r in results]})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.9, [check("queried", True, "consulta local")])


class Forget(Skill):
    name = "memory.forget"
    description = "Esquecer um fato registrado."
    category = "memory"
    inputs = schema({"subject": string(80)}, ("subject",))
    risk = Risk.HIGH
    reversible = False

    def execute(self, ctx, subject: str) -> SkillResult:
        if not ctx.memory.forget_fact(subject):
            return SkillResult(False, error=f"não há memória sobre {subject}", error_kind="NOT_FOUND")
        return SkillResult(True, f"Memória sobre {subject} removida.", [], {"subject": subject})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        gone = ctx.memory.semantic.get(result.data["subject"]) is None
        return VerificationResult.from_checks([check("removed", gone, "fato ausente da base")])


class SetPreference(Skill):
    name = "memory.set_preference"
    description = "Atualizar uma preferência do usuário (" + ", ".join(sorted(ALLOWED)) + ")."
    category = "memory"
    inputs = schema({"name": string(40, enum=sorted(ALLOWED)), "value": string(200)}, ("name", "value"))
    risk = Risk.LOW

    def execute(self, ctx, name: str, value: str) -> SkillResult:
        try:
            stored = ctx.memory.preferences.set(name, value)
        except ValueError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        return SkillResult(True, f"Preferência {ALLOWED[name].lower()} definida.", [], {"name": name, "value": stored})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        ok = ctx.memory.preferences.get(result.data["name"]) == result.data["value"]
        return VerificationResult.from_checks([check("persisted", ok, "preferência lida de volta")])


SKILLS = (Remember, Recall, Forget, SetPreference)
