"""Skills do SECOND BRAIN: o mesmo caminho para voz, texto e o HUB 2.

Toda escrita passa pelo Execution Engine (autonomia central, autorização e auditoria) e cada
skill verifica o resultado lendo de volta do banco — nunca confia só no que executou.
Operações rotineiras e reversíveis (registrar, editar, concluir, adiar, mandar para a lixeira)
são automáticas; a exclusão DEFINITIVA é irreversível e exige autorização específica.
"""
from __future__ import annotations

from pathlib import Path

from ...secondbrain import timeutil
from ...secondbrain.capture import confirmation_text
from ...secondbrain.models import KINDS, RELATIONS, STATUSES
from ...secondbrain.queries import answer
from ...secondbrain.service import EXPORT_FORMATS, NeedsClarification, SecondBrainError, brief, describe_record
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

CATEGORY = "second_brain"


def _service(ctx):
    service = (ctx.extras or {}).get("second_brain")
    if service is None:
        raise SecondBrainError("Second Brain indisponível nesta execução")
    return service


def _fail(exc: Exception) -> SkillResult:
    if isinstance(exc, NeedsClarification):
        return SkillResult(True, exc.question, ["nada foi alterado: esclarecimento necessário"],
                           {"clarify": True, "candidates": exc.candidates})
    return SkillResult(False, error=str(exc), error_kind="INVALID_ARGUMENT" if isinstance(exc, SecondBrainError)
                       else "UNKNOWN_ERROR")


class _SBSkill(Skill):
    category = CATEGORY
    risk = Risk.LOW

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        if result.data.get("clarify"):
            return VerificationResult("VERIFIED", 0.9, [check("nothing_recorded", True,
                                                              "pergunta de esclarecimento; nada gravado")])
        record_id = result.data.get("id")
        if not record_id:
            return VerificationResult("VERIFIED", 0.9, [check("read_only", True, "consulta ao banco local")])
        service = _service(ctx)
        return VerificationResult.from_checks(self.checks(service, service.get(record_id), args, result))

    def checks(self, service, record, args, result) -> list:
        return [check("persisted", record is not None, "registro lido de volta do banco")]


class Capture(_SBSkill):
    name = "secondbrain.capture"
    description = ("Registrar no Second Brain uma tarefa, compromisso, estudo, projeto, ideia, nota, pessoa, rotina "
                   "ou prazo, com data/hora em português e lembrete opcional.")
    inputs = schema({"text": string(600), "kind": string(20, enum=sorted(KINDS)), "title": string(200),
                     "when": string(120), "priority": {"type": "integer", "minimum": 1, "maximum": 4},
                     "project": string(80), "remind": {"type": "boolean"},
                     "leads": {"type": "array", "items": {"type": "integer"}}, "record": string(40),
                     "body": string(4000)}, ("text",))

    def describe_action(self, args):
        return f"registrar no Second Brain: {args.get('title') or args.get('text', '')[:80]}"

    def execute(self, ctx, text: str, kind: str | None = None, title: str | None = None, when: str | None = None,
                priority: int | None = None, project: str | None = None, remind: bool | None = None,
                leads: list | None = None, record: str | None = None, body: str = "") -> SkillResult:
        capture = (ctx.extras or {}).get("capture")
        if capture is None:
            return SkillResult(False, error="Second Brain indisponível nesta execução", error_kind="UNSUPPORTED")
        try:
            result = capture.explicit(text, kind=kind, title=title, when=when, priority=priority, project=project,
                                      origin=(ctx.extras or {}).get("origin", "user"), remind=remind,
                                      leads=[int(x) for x in leads] if leads else None, record_id=record,
                                      body=body)
        except Exception as exc:
            return _fail(exc)
        if result.question:
            return SkillResult(True, result.question, ["nada foi registrado: esclarecimento necessário"],
                               {"clarify": True, "pending": result.pending})
        record = result.records[0]
        reminders = _service(ctx).store.reminders_for(record.id)
        return SkillResult(True, confirmation_text(result, now=_service(ctx).now_wall()),
                           [f"{record.label.lower()} {record.id}"] + [f"lembrete {r.at_local}" for r in reminders]
                           + [f"conflito com {c.id}" for c in result.conflicts],
                           {"id": record.id, "record": record.to_dict(),
                            "reminders": [r.to_dict() for r in reminders],
                            "conflicts": [brief(c) for c in result.conflicts]})

    def checks(self, service, record, args, result):
        checks = [check("persisted", record is not None and not record.deleted_at, "registro lido de volta do banco")]
        expected = {r["id"] for r in result.data.get("reminders") or []}
        if record is not None and expected:
            stored = {r.id for r in service.store.reminders_for(record.id)}
            checks.append(check("reminder_scheduled", expected <= stored, "lembrete agendado no banco"))
        return checks


class Query(_SBSkill):
    name = "secondbrain.query"
    description = ("Responder perguntas sobre os registros salvos: prioridades de hoje, o que falta na semana, "
                   "atrasados, ideias de um projeto, dependências, decisões, próximos compromissos, busca.")
    inputs = schema({"question": string(400)}, ("question",))
    risk = Risk.NONE

    def execute(self, ctx, question: str) -> SkillResult:
        try:
            result = answer(_service(ctx), question)
        except Exception as exc:
            return _fail(exc)
        return SkillResult(True, result.text, [f"{len(result.records)} registro(s) consultado(s)"],
                           {"answer": result.to_dict()})


class _Target(_SBSkill):
    """Skills que agem sobre um registro existente (por id ou pelo título)."""

    open_only = True

    def target(self, ctx, ref: str, kinds=None):
        return _service(ctx).resolve(ref, kinds=kinds, open_only=self.open_only)


class Complete(_Target):
    name = "secondbrain.complete"
    description = "Marcar uma tarefa, estudo, prazo ou rotina como concluído (recorrentes avançam para a próxima)."
    inputs = schema({"ref": string(200)}, ("ref",))

    def execute(self, ctx, ref: str) -> SkillResult:
        try:
            record = self.target(ctx, ref)
            before = record.due_local
            record = _service(ctx).complete(record.id, origin=(ctx.extras or {}).get("origin", "user"))
        except Exception as exc:
            return _fail(exc)
        if record.status == "done":
            text = f"Concluído: {record.title}."
        else:
            text = f"Ocorrência concluída: {record.title}. Próxima: {describe_record(record, now=_service(ctx).now_wall())}."
        return SkillResult(True, text, [record.id], {"id": record.id, "before": before, "status": record.status,
                                                    "due": record.due_local})

    def checks(self, service, record, args, result):
        if record is None:
            return [check("persisted", False, "registro não encontrado")]
        if result.data.get("status") == "done":
            return [check("status_done", record.status == "done", f"estado no banco: {record.status}")]
        return [check("advanced", record.due_local != result.data.get("before"), "próxima ocorrência gravada")]


class Update(_Target):
    name = "secondbrain.update"
    description = "Editar um registro: título, descrição, data, prioridade, estado, categoria ou projeto."
    inputs = schema({"ref": string(200), "title": string(200), "body": string(2000), "when": string(120),
                     "priority": {"type": "integer", "minimum": 1, "maximum": 4}, "status": string(20, enum=list(STATUSES)),
                     "kind": string(20, enum=sorted(KINDS)), "project": string(80), "confirm": {"type": "boolean"}},
                    ("ref",))
    open_only = False

    def execute(self, ctx, ref: str, **fields) -> SkillResult:
        changes = {}
        for key in ("title", "body", "priority", "status", "kind"):
            if fields.get(key) not in (None, ""):
                changes[key] = fields[key]
        if fields.get("project"):
            changes["project_id"] = fields["project"]
        if fields.get("confirm"):
            changes["confirmed"] = True
        try:
            record = self.target(ctx, ref)
            kwargs = {"when": fields["when"]} if fields.get("when") else {}
            record = _service(ctx).update(record.id, origin=(ctx.extras or {}).get("origin", "user"), **kwargs, **changes)
        except Exception as exc:
            return _fail(exc)
        service = _service(ctx)
        text = f"Atualizado: {describe_record(record, now=service.now_wall())}."
        conflicts = service.conflicts(record) if fields.get("when") or changes.get("status") else []
        if conflicts:
            text += " Atenção: conflita com " + "; ".join(describe_record(c, now=service.now_wall())
                                                          for c in conflicts[:3]) + "."
        return SkillResult(True, text, [record.id],
                           {"id": record.id, "conflicts": [brief(c) for c in conflicts],
                            "expected": {k: v for k, v in changes.items() if k in ("title", "status", "priority",
                                                                                   "kind")}})

    def checks(self, service, record, args, result):
        if record is None:
            return [check("persisted", False, "registro não encontrado")]
        expected = result.data.get("expected") or {}
        checks = [check(f"field_{k}", getattr(record, k) == (v if k != "title" else " ".join(str(v).split())),
                        f"{k} no banco") for k, v in expected.items()]
        return checks or [check("persisted", True, "registro lido de volta do banco")]


class Snooze(_SBSkill):
    name = "secondbrain.snooze"
    description = "Adiar um lembrete por alguns minutos (o último avisado, ou o de um registro indicado)."
    inputs = schema({"minutes": {"type": "integer", "minimum": 1, "maximum": 1440}, "ref": string(200)}, ("minutes",))

    def execute(self, ctx, minutes: int, ref: str | None = None) -> SkillResult:
        service = _service(ctx)
        reminders = service.reminders
        if reminders is None:
            return SkillResult(False, error="agendador de lembretes indisponível", error_kind="UNSUPPORTED")
        try:
            if ref:
                record = service.resolve(ref)
                candidates = service.store.reminders_for(record.id)
                if not candidates:
                    return SkillResult(False, error=f"\"{record.title}\" não tem lembrete agendado",
                                       error_kind="NOT_FOUND")
                target = candidates[0]
            else:
                target = reminders.latest_fired() or next(iter(service.store.upcoming_reminders(
                    after=service.now(), limit=1)), None)
                if target is None:
                    return SkillResult(False, error="não há lembrete recente para adiar", error_kind="NOT_FOUND")
            rem = reminders.snooze(target.id, minutes)
        except Exception as exc:
            return _fail(exc)
        record = service.get(rem.record_id)
        when = timeutil.describe(timeutil.from_epoch(rem.next_at, rem.tz), now=service.now_wall())
        return SkillResult(True, f"Lembrete adiado: {record.title if record else ''} — {when}.", [rem.id],
                           {"reminder_id": rem.id, "until": rem.next_at})

    def verify(self, ctx, args, result):
        if not result.success or result.data.get("clarify"):
            return super().verify(ctx, args, result)
        rem = _service(ctx).store.reminder(result.data["reminder_id"])
        ok = rem is not None and rem.status == "scheduled" and abs(rem.next_at - result.data["until"]) < 1
        return VerificationResult.from_checks([check("rescheduled", ok, "novo horário gravado no banco")])


class Delete(_Target):
    name = "secondbrain.delete"
    description = "Mandar um registro para a lixeira (recuperável) ou excluí-lo definitivamente (irreversível)."
    inputs = schema({"ref": string(200), "permanent": {"type": "boolean"}}, ("ref",))
    open_only = False
    risk = Risk.LOW

    def risk_for(self, args):
        return Risk.CRITICAL if args.get("permanent") else Risk.LOW

    reversible = True                     # a lixeira é reversível; a definitiva é CRÍTICA e sempre pede autorização
    sensitive = ""

    def sensitive_for(self, args):
        return "permanent_delete" if args.get("permanent") else ""

    def describe_action(self, args):
        if args.get("permanent"):
            return "EXCLUIR DEFINITIVAMENTE do Second Brain (sem recuperação)"
        return "mandar para a lixeira"

    def describe_resource(self, ctx, args):
        ref = str(args.get("ref", ""))
        service = _service(ctx)
        record = service.store.get(ref) if ref.startswith("r_") else None
        if record is None:
            return f"\"{ref}\""
        state = " (na lixeira)" if record.deleted_at else ""
        return f"{record.label.lower()} \"{record.title}\"{state}"

    def execute(self, ctx, ref: str, permanent: bool = False) -> SkillResult:
        service = _service(ctx)
        try:
            record = service.store.get(ref) if ref.startswith("r_") else None
            if record is None:
                record = self.target(ctx, ref)
            service.delete(record.id, permanent=permanent, origin=(ctx.extras or {}).get("origin", "user"))
        except Exception as exc:
            return _fail(exc)
        text = (f"Excluído definitivamente: {record.title}." if permanent else
                f"Enviado para a lixeira: {record.title}. Pode ser restaurado.")
        return SkillResult(True, text, [record.id], {"id": record.id, "permanent": permanent})

    def verify(self, ctx, args, result):
        if not result.success or result.data.get("clarify"):
            return super().verify(ctx, args, result)
        record = _service(ctx).get(result.data["id"])
        if result.data["permanent"]:
            return VerificationResult.from_checks([check("purged", record is None, "registro ausente do banco")])
        return VerificationResult.from_checks([check("in_trash", record is not None and bool(record.deleted_at),
                                                     "registro marcado como excluído (recuperável)")])


class Restore(_SBSkill):
    name = "secondbrain.restore"
    description = "Restaurar um registro da lixeira."
    inputs = schema({"ref": string(200)}, ("ref",))

    def execute(self, ctx, ref: str) -> SkillResult:
        service = _service(ctx)
        record = service.store.get(ref) if ref.startswith("r_") else None
        if record is None:
            matches = [r for r in service.trash() if ref.casefold() in r.title.casefold()]
            if not matches:
                return SkillResult(False, error=f"nada na lixeira sobre \"{ref}\"", error_kind="NOT_FOUND")
            record = matches[0]
        try:
            record = service.restore(record.id)
        except Exception as exc:
            return _fail(exc)
        return SkillResult(True, f"Restaurado: {record.title}.", [record.id], {"id": record.id})

    def checks(self, service, record, args, result):
        return [check("restored", record is not None and not record.deleted_at, "registro ativo no banco")]


class Archive(_Target):
    name = "secondbrain.archive"
    description = "Arquivar (ou desarquivar) um registro: sai das listas sem ser excluído."
    inputs = schema({"ref": string(200), "archived": {"type": "boolean"}}, ("ref",))
    open_only = False

    def execute(self, ctx, ref: str, archived: bool = True) -> SkillResult:
        try:
            record = _service(ctx).archive(self.target(ctx, ref).id, archived=archived,
                                           origin=(ctx.extras or {}).get("origin", "user"))
        except Exception as exc:
            return _fail(exc)
        return SkillResult(True, ("Arquivado: " if archived else "Desarquivado: ") + record.title + ".", [record.id],
                           {"id": record.id, "archived": archived})

    def checks(self, service, record, args, result):
        return [check("archived", record is not None and bool(record.archived_at) == result.data["archived"],
                      "estado de arquivamento no banco")]


class Relate(_SBSkill):
    name = "secondbrain.relate"
    description = "Relacionar dois registros (depende de, relacionado a, parte de, sobre)."
    inputs = schema({"source": string(200), "target": string(200), "type": string(20, enum=sorted(RELATIONS))},
                    ("source", "target"))

    def execute(self, ctx, source: str, target: str, type: str = "related") -> SkillResult:
        service = _service(ctx)
        try:
            a, b = service.resolve(source), service.resolve(target)
            service.relate(a.id, b.id, type)
        except Exception as exc:
            return _fail(exc)
        return SkillResult(True, f"\"{a.title}\" {RELATIONS[type]} \"{b.title}\".", [a.id, b.id],
                           {"id": a.id, "target": b.id, "type": type})

    def checks(self, service, record, args, result):
        stored = record is not None and any(
            r.get("type") == result.data["type"] and result.data["target"] in (r.get("src"), r.get("dst"))
            for r in service.store.relations(record.id))
        return [check("related", stored, "relação gravada no banco")]


class Dismiss(_SBSkill):
    name = "secondbrain.dismiss"
    description = "Marcar um lembrete como ciente (encerra as repetições; recorrentes seguem para a próxima)."
    inputs = schema({"reminder": string(40)}, ("reminder",))
    expose_to_llm = False

    def execute(self, ctx, reminder: str) -> SkillResult:
        service = _service(ctx)
        if service.reminders is None:
            return SkillResult(False, error="agendador de lembretes indisponível", error_kind="UNSUPPORTED")
        rem = service.reminders.dismiss(reminder)
        if rem is None:
            return SkillResult(False, error="lembrete não encontrado", error_kind="NOT_FOUND")
        record = service.get(rem.record_id)
        return SkillResult(True, f"Ciente: {record.title if record else 'lembrete'}.", [rem.id],
                           {"reminder_id": rem.id, "status": rem.status, "next_at": rem.next_at})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        rem = _service(ctx).store.reminder(result.data["reminder_id"])
        ok = rem is not None and (rem.status == "done" or rem.next_at == result.data["next_at"])
        return VerificationResult.from_checks([check("dismissed", ok, "estado do lembrete gravado")])


class EmptyTrash(_SBSkill):
    name = "secondbrain.empty_trash"
    description = "Esvaziar a lixeira do Second Brain (exclusão definitiva de tudo que está nela)."
    inputs = schema({})
    risk = Risk.CRITICAL
    reversible = False
    sensitive = "permanent_delete"
    expose_to_llm = False

    def describe_action(self, args):
        return "ESVAZIAR A LIXEIRA do Second Brain (exclusão definitiva, sem recuperação)"

    def describe_resource(self, ctx, args):
        return f"{len(_service(ctx).trash())} registro(s) na lixeira"

    def execute(self, ctx, **_) -> SkillResult:
        service = _service(ctx)
        count = service.empty_trash(origin=(ctx.extras or {}).get("origin", "user"))
        return SkillResult(True, f"Lixeira esvaziada: {count} registro(s) excluído(s) definitivamente.", [],
                           {"count": count})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        left = len(_service(ctx).trash())
        return VerificationResult.from_checks([check("trash_empty", left == 0, f"{left} item(ns) na lixeira")])


class Conflicts(_SBSkill):
    name = "secondbrain.conflicts"
    description = "Verificar compromissos que se sobrepõem na agenda (de hoje até os próximos dias)."
    inputs = schema({"days": {"type": "integer", "minimum": 1, "maximum": 90}})
    risk = Risk.NONE

    def execute(self, ctx, days: int = 14) -> SkillResult:
        service = _service(ctx)
        pairs = service.agenda_conflicts(days=int(days))
        now = service.now_wall()
        if not pairs:
            return SkillResult(True, f"Nenhum conflito de horário na agenda dos próximos {days} dias.", [],
                               {"conflicts": []})
        lines = [f"{describe_record(a, now=now)} × {describe_record(b, now=now)}" for a, b in pairs[:6]]
        more = f" (e mais {len(pairs) - 6})" if len(pairs) > 6 else ""
        return SkillResult(True, f"{len(pairs)} conflito(s) de horário: " + "; ".join(lines) + more + ".",
                           [f"{a.id}×{b.id}" for a, b in pairs],
                           {"conflicts": [[brief(a), brief(b)] for a, b in pairs]})


def _export_target(path: str | None, fmt: str) -> Path:
    """Destino da exportação: um arquivo NOVO, .json/.csv, dentro da pasta pessoal do usuário ou da
    pasta de dados do JARVIS (um caminho vindo de texto da tela ou de documento não sai dali)."""
    import time

    from ...config import paths
    if not path:
        return paths.data_dir() / "exports" / f"jarvis-memoria-{time.strftime('%Y%m%d-%H%M%S')}.{fmt}"
    target = Path(path).expanduser()
    if target.suffix.lower() != f".{fmt}":
        target = target.with_suffix(f".{fmt}")
    resolved = target.resolve()
    allowed = [Path.home().resolve(), paths.data_dir().resolve()]
    if not any(resolved == root or root in resolved.parents for root in allowed):
        raise SecondBrainError("exporto apenas para a sua pasta pessoal ou para a pasta de dados do JARVIS")
    return resolved


class Export(_SBSkill):
    name = "secondbrain.export"
    description = ("Exportar a memória pessoal (tarefas, compromissos, ideias, notas...) para um arquivo novo "
                   "JSON (completo) ou CSV (planilha).")
    inputs = schema({"format": string(8, enum=list(EXPORT_FORMATS)), "path": string(400),
                     "include_deleted": {"type": "boolean"}})

    def describe_action(self, args):
        return f"exportar a memória pessoal em {str(args.get('format') or 'json').upper()}"

    def execute(self, ctx, format: str = "json", path: str | None = None, include_deleted: bool = False) -> SkillResult:
        service = _service(ctx)
        try:
            target = _export_target(path, format)
            info = service.export(target, fmt=format, include_deleted=include_deleted)
        except Exception as exc:
            return _fail(exc)
        return SkillResult(True, f"Exportei {info['count']} registro(s) em {info['format'].upper()}: {info['path']}",
                           [info["path"]], {"export": info})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        import json
        info = result.data.get("export") or {}
        path = Path(info.get("path", ""))
        ok = path.is_file() and path.stat().st_size > 0
        detail = "arquivo criado"
        if ok and info.get("format") == "json":
            try:
                ok = json.loads(path.read_text(encoding="utf-8")).get("count") == info.get("count")
                detail = "arquivo relido: contagem confere"
            except ValueError:
                ok, detail = False, "JSON ilegível"
        return VerificationResult.from_checks([check("export_file", ok, detail)])


class Backup(_SBSkill):
    name = "memory.backup"
    description = ("Fazer agora um backup do banco do JARVIS (memórias, Second Brain, lembretes, grafo e "
                   "inventário da rede).")
    inputs = schema({})

    def describe_action(self, args):
        return "criar um backup do banco do JARVIS"

    def execute(self, ctx, **_) -> SkillResult:
        from ...memory import backup
        service = _service(ctx)
        settings = ctx.settings() if callable(ctx.settings) else ctx.settings
        keep = int(getattr(settings, "backup_keep", 10) or 10)
        try:
            path = backup.create_backup(service.db, reason="manual", keep=keep)
        except Exception as exc:
            return SkillResult(False, error=f"backup falhou: {exc}", error_kind="UNKNOWN_ERROR")
        return SkillResult(True, f"Backup criado: {path}", [str(path)], {"backup": str(path)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        from ...memory.store import verify_database_file
        ok, detail = verify_database_file(result.data.get("backup", ""))
        return VerificationResult.from_checks([check("backup_integrity", ok, detail)])


SKILLS = (Capture, Query, Complete, Update, Snooze, Delete, Restore, Archive, Relate, Dismiss, EmptyTrash, Conflicts,
          Export, Backup)
