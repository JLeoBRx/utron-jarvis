"""Skills do próprio assistente — recuperadas do JARVIS original.

* ``jarvis.shutdown``: encerrar o JARVIS (no original, "encerrar jarvis" só respondia "Encerrando,
  senhor."); passa pela confirmação do executor, como toda ação de risco alto.
* ``memory.session_note`` / ``memory.profile``: ferramentas ``add_session_note`` e ``get_profile``.
* ``diagnostics.audit``: ferramenta ``read_audit`` (o registro já existia, só não era legível pelo
  modelo).
"""
from __future__ import annotations

import time

from ...core.events import EventType
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string


class Shutdown(Skill):
    name = "jarvis.shutdown"
    description = "Encerrar o JARVIS (fecha a interface, a voz e os serviços em ordem)."
    category = "assistant"
    inputs = schema({})
    risk = Risk.HIGH
    reversible = False
    expose_to_llm = False                 # só por pedido direto do usuário

    def execute(self, ctx, **_) -> SkillResult:
        if ctx.emit is None:
            return SkillResult(False, error="encerramento indisponível nesta execução", error_kind="UNAVAILABLE")
        ctx.emit(EventType.SHUTDOWN_REQUESTED, reason="pedido do usuário", at=time.time())
        return SkillResult(True, "Encerrando, senhor.", ["pedido de encerramento enviado"], {"requested": True})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("requested", True, "pedido de encerramento publicado")])


class SessionNote(Skill):
    name = "memory.session_note"
    description = ("Anotar um contexto da sessão de trabalho atual (ex.: 'estamos ajustando o Kd do Noctário'). "
                   "Entra no contexto das próximas respostas; nunca senhas ou dados sensíveis.")
    category = "memory"
    inputs = schema({"note": string(300)}, ("note",))
    risk = Risk.LOW

    def execute(self, ctx, note: str) -> SkillResult:
        try:
            stored = ctx.memory.add_session_note(note)
        except ValueError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        return SkillResult(True, "Nota da sessão registrada.", [stored[:60]], {"note": stored})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        notes = [n["note"] for n in ctx.memory.session_notes()]
        ok = result.data["note"] in notes
        return VerificationResult.from_checks([check("persisted", ok, "nota lida de volta" if ok else
                                                     "a nota não foi encontrada após gravar")])


class Profile(Skill):
    name = "memory.profile"
    description = "Ler o perfil e as preferências do usuário (nome, tratamento, cidade, idioma, editor...)."
    category = "memory"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        prefs = ctx.memory.preferences.all()
        if not prefs:
            return SkillResult(True, "Nenhuma preferência registrada.", [], {"preferences": {}})
        text = "; ".join(f"{k}: {v}" for k, v in sorted(prefs.items()))
        return SkillResult(True, "Perfil: " + text, [], {"preferences": prefs})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.95, [check("read", True, "lido das preferências")])


class ReadAudit(Skill):
    name = "diagnostics.audit"
    description = "Ler as últimas entradas do registro de auditoria local (ações executadas e verificadas)."
    category = "diagnostics"
    inputs = schema({"limit": {"type": "integer", "minimum": 1, "maximum": 20}})
    risk = Risk.NONE

    def execute(self, ctx, limit: int = 10) -> SkillResult:
        rows = ctx.memory.db.query("SELECT source, action, detail, verified, created_at FROM audit "
                                   "ORDER BY id DESC LIMIT ?", (int(limit),))
        if not rows:
            return SkillResult(True, "O registro de auditoria está vazio.", [], {"entries": []})
        entries = [{"source": r["source"], "action": r["action"], "detail": r["detail"],
                    "verified": None if r["verified"] is None else bool(r["verified"]),
                    "at": time.strftime("%d/%m %H:%M", time.localtime(r["created_at"]))} for r in rows]
        text = "; ".join(f"{e['at']} {e['action']}" + ("" if e["verified"] is None else
                                                      (" (verificado)" if e["verified"] else " (não verificado)"))
                         for e in entries)
        return SkillResult(True, "Auditoria: " + text, [], {"entries": entries})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.95, [check("read", True, "lido do banco local")])


SKILLS = (Shutdown, SessionNote, Profile, ReadAudit)
