"""Skills de imaginação: conceitos, mundos, ramificações e imagens (delegam ao Imagination Core)."""
from __future__ import annotations

from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string


class _CreativeSkill(Skill):
    category = "imagination"
    risk = Risk.NONE
    timeout = 300.0

    def _core(self, ctx):
        if ctx.imagination is None:
            raise RuntimeError("Imagination Core indisponível")
        return ctx.imagination

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        stored = bool(result.data.get("id"))
        return VerificationResult.from_checks([check("persisted", stored, "criação registrada na memória")])


class Imagine(_CreativeSkill):
    name = "imagination.imagine"
    description = "Imaginar um conceito original (facetas, relações, cenário e visualização)."
    inputs = schema({"idea": string(400)}, ("idea",))

    def execute(self, ctx, idea: str) -> SkillResult:
        concept = self._core(ctx).imagine(idea, cancel=ctx.cancel)
        return SkillResult(True, concept.describe(), [f"gerador: {concept.generator}"], concept.to_dict())


class CreateWorld(_CreativeSkill):
    name = "imagination.create_world"
    description = "Construir um mundo fictício com camadas (mapa, clima, cultura, história...)."
    inputs = schema({"idea": string(400)}, ("idea",))

    def execute(self, ctx, idea: str) -> SkillResult:
        node = self._core(ctx).worlds.create(idea, cancel=ctx.cancel)
        self._core(ctx).current_world_node = node.id
        return SkillResult(True, node.describe(), [f"gerador: {node.generator}"], node.to_dict())


class Branch(_CreativeSkill):
    name = "imagination.branch"
    description = "Gerar e comparar alternativas (A-D) para uma ideia: custo, tempo, qualidade, complexidade, risco."
    inputs = schema({"idea": string(400)}, ("idea",))

    def execute(self, ctx, idea: str) -> SkillResult:
        result = self._core(ctx).scenarios.branch(idea, cancel=ctx.cancel)
        text = "; ".join(f"{o['id']}: {o['title']}" for o in result["options"])
        return SkillResult(True, f"{text}. Recomendada: {result['recommended']}.", [f"gerador: {result['generator']}"],
                           result)


class GenerateImage(_CreativeSkill):
    name = "imagination.generate_image"
    description = "Gerar uma imagem de um conceito (requer modelo de imagem local)."
    inputs = schema({"subject": string(400)}, ("subject",))

    def execute(self, ctx, subject: str) -> SkillResult:
        core = self._core(ctx)
        status = core.images.status(refresh=True)
        if not status["available"]:
            return SkillResult(False, error=status["reason"], error_kind="UNSUPPORTED")
        concept = core.imagine(subject, cancel=ctx.cancel, with_image=False, with_scenario=False)
        path = core.render(concept, cancel=ctx.cancel)
        if not path:
            return SkillResult(False, error="o provedor de imagem falhou", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"Imagem gerada: {path}", [path], {"id": concept.id, "path": path})

    def verify(self, ctx, args, result):
        import os
        if not result.success:
            return super().verify(ctx, args, result)
        ok = os.path.isfile(result.data["path"]) and os.path.getsize(result.data["path"]) > 0
        return VerificationResult.from_checks([check("image_file", ok, result.data["path"])])


SKILLS = (Imagine, CreateWorld, Branch, GenerateImage)
