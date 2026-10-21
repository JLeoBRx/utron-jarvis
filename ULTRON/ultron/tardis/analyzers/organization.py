"""Organização da memória pessoal e rotinas — análise determinística (sem modelo).

Organização: atrasados, conflitos de agenda, duplicados (mesmo título normalizado), tarefas sem data e
registros inferidos aguardando revisão. Para duplicados, PROPÕE arquivar as cópias mais novas (ação
reversível que o JARVIS só executa com confirmação). Rotinas: lembretes futuros, recorrências e
automações configuradas.
"""
from __future__ import annotations

import time

from ..protocol import ProposedAction, TaskFailed, TaskResult
from . import DETERMINISTIC, Run, normalize

SOURCE = "memória pessoal"


def _join(counts: list[tuple[int, str, str]]) -> str:
    """Só as contagens diferentes de zero, em português: "1 tarefa sem data e 2 conflitos de horário"."""
    parts = [f"{n} {one if n == 1 else many}" for n, one, many in counts if n]
    if not parts:
        return "nada"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]


def organizacao(run: Run, data: dict) -> TaskResult:
    sb = run.ctx.second_brain
    if sb is None:
        raise TaskFailed("NO_DATA", "memória pessoal indisponível")
    run.envelope.model = DETERMINISTIC
    items: list[dict] = []
    actions: list[ProposedAction] = []
    overdue = sb.overdue(limit=50)
    for record in overdue:
        items.append({"title": f"Atrasado: {record.title}", "detail": f"{record.kind} · previsto {record.due_local}",
                      "source": f"{SOURCE} ({record.id})", "severity": "alta"})
    run.check()
    conflicts = sb.agenda_conflicts(days=14)
    for a, b in conflicts:
        items.append({"title": f"Conflito de horário: {a.title} × {b.title}",
                      "detail": f"{a.due_local} e {b.due_local}", "source": f"{SOURCE} ({a.id}, {b.id})",
                      "severity": "média"})
    run.check()
    groups: dict[str, list] = {}
    for record in sb.list(status=("open", "in_progress", "waiting"), limit=1000):
        key = f"{record.kind}|{normalize(record.title)}"
        groups.setdefault(key, []).append(record)
    duplicates = [sorted(group, key=lambda r: r.created_at) for group in groups.values() if len(group) > 1]
    for group in duplicates:
        keep, extra = group[0], group[1:]
        items.append({"title": f"Duplicado: {keep.title} ({len(group)}×)",
                      "detail": f"{keep.kind} · mantém o mais antigo ({keep.id})",
                      "source": f"{SOURCE} ({', '.join(r.id for r in group)})", "severity": "média"})
        if run.ctx.has_skill("secondbrain.archive"):
            for record in extra[:5]:
                actions.append(ProposedAction(f"arquivar a cópia “{record.title}” ({record.id})", "secondbrain.archive",
                                              {"ref": record.id},
                                              f"mesmo título e tipo de {keep.id}; arquivar é reversível"))
    undated = [r for r in sb.list(kinds=("task", "deadline", "study"), status=("open", "in_progress", "waiting"),
                                  limit=500) if r.due_at is None]
    for record in undated[:20]:
        age = (time.time() - record.created_at) / 86400 if record.created_at else 0
        items.append({"title": f"Sem data: {record.title}", "detail": f"{record.kind} · aberto há {age:.0f} dia(s)",
                      "source": f"{SOURCE} ({record.id})", "severity": "baixa"})
    review = sb.review_queue(limit=20)
    for record in review:
        items.append({"title": f"Aguardando revisão: {record.title}", "detail": "registrado sozinho (inferido)",
                      "source": f"{SOURCE} ({record.id})", "severity": "baixa"})
    if not items:
        return TaskResult("Nada a organizar: sem atrasados, conflitos, duplicados, tarefas sem data ou "
                          "registros aguardando revisão.", sources=[SOURCE])
    summary = _join([(len(overdue), "registro atrasado", "registros atrasados"),
                     (len(conflicts), "conflito de horário", "conflitos de horário"),
                     (len(duplicates), "grupo de duplicados", "grupos de duplicados"),
                     (len(undated), "tarefa sem data", "tarefas sem data"),
                     (len(review), "registro aguardando revisão", "registros aguardando revisão")]) + "."
    summary = summary[:1].upper() + summary[1:]
    return TaskResult(summary, items, [SOURCE], actions,
                      {"overdue": len(overdue), "conflicts": len(conflicts), "duplicates": len(duplicates),
                       "undated": len(undated), "review": len(review)})


def rotinas(run: Run, data: dict) -> TaskResult:
    sb = run.ctx.second_brain
    memory = run.ctx.memory
    if sb is None and memory is None:
        raise TaskFailed("NO_DATA", "memória pessoal indisponível")
    run.envelope.model = DETERMINISTIC
    items: list[dict] = []
    upcoming = []
    if sb is not None and getattr(sb, "reminders", None) is not None:
        upcoming = sb.reminders.upcoming(limit=20)
        for reminder in upcoming:
            items.append({"title": f"Lembrete: {reminder['title']}", "detail": reminder.get("when_text", ""),
                          "source": f"{SOURCE} ({reminder.get('record_id')})"})
    recurring = []
    if sb is not None:
        recurring = [r for r in sb.list(limit=1000) if r.recurrence]
        for record in recurring:
            items.append({"title": f"Recorrente: {record.title}", "detail": f"{record.recurrence}"
                          + (f" · próximo {record.due_local}" if record.due_local else ""),
                          "source": f"{SOURCE} ({record.id})"})
    automations = []
    if memory is not None:
        automations = memory.procedural.automations()
        for automation in automations:
            state = "ativa" if automation.get("enabled", True) else "pausada"
            items.append({"title": f"Automação: {automation.get('name')}",
                          "detail": f"{state} · “{automation.get('trigger_text') or automation.get('trigger', '')}”",
                          "source": "automações"})
    if not items:
        return TaskResult("Nenhum lembrete futuro, recorrência ou automação registrada.", sources=[SOURCE])
    summary = _join([(len(upcoming), "lembrete futuro", "lembretes futuros"),
                     (len(recurring), "registro recorrente", "registros recorrentes"),
                     (len(automations), "automação", "automações")]) + "."
    summary = summary[:1].upper() + summary[1:]
    return TaskResult(summary, items, sorted({i["source"].split(" (")[0] for i in items}),
                      data={"reminders": len(upcoming), "recurring": len(recurring), "automations": len(automations)})
