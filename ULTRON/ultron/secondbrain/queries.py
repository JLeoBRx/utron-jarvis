"""QUERIES — perguntas em português respondidas SÓ com o que está salvo no Second Brain.

"O que ainda preciso terminar esta semana?", "Quais ideias salvei para o projeto Atlas?",
"O que está atrasado?", "Quais tarefas dependem do relatório?", "O que eu havia decidido
sobre o orçamento?", "Quais são minhas prioridades de hoje?"...

Sem registro correspondente, a resposta diz que não encontrou — nunca completa com suposições.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from . import parsing, timeutil
from .models import KIND_PLURALS, KINDS, Record
from .service import NeedsClarification, SecondBrainError, SecondBrainService, describe_record

MAX_ITEMS = 8


@dataclass
class Answer:
    text: str
    records: list = field(default_factory=list)
    kind: str = "list"                  # list | empty | clarify | error
    query: str = ""

    def to_dict(self) -> dict:
        return {"text": self.text, "records": [r.to_dict() if isinstance(r, Record) else r for r in self.records],
                "kind": self.kind, "query": self.query}


def _items(records: list[Record], now: dt.datetime, *, limit: int = MAX_ITEMS) -> str:
    lines = [describe_record(r, now=now) for r in records[:limit]]
    extra = f" (e mais {len(records) - limit})" if len(records) > limit else ""
    return "; ".join(lines) + extra


def _topic(match: re.Match, raw: str) -> str:
    """O trecho do texto ORIGINAL (com acentos) correspondente ao grupo 'topic'."""
    start, end = match.span("topic")
    return raw[start:end].strip(" ?.!,;:")


QUESTION_PATTERNS = (
    ("today", re.compile(r"\b(prioridades|o que (eu )?tenho (para|pra) hoje|minha agenda de hoje|agenda de hoje|"
                         r"o que tenho hoje|meu dia)\b")),
    ("week", re.compile(r"\b(o que|quais tarefas|que tarefas)\b.*\b(preciso|tenho que|falta|faltam|devo)\b.*"
                        r"\b(terminar|fazer|entregar|concluir|resolver)\b.*\b(semana)\b|"
                        r"\bpendencias da semana\b|\bo que falta (nesta|esta|essa) semana\b")),
    ("overdue", re.compile(r"\b(atrasad[oa]s?|vencid[oa]s?|o que (eu )?atrasei|em atraso)\b")),
    ("ideas", re.compile(r"\b(quais|que|minhas)\s+ideias\b.*?\b(para|pro|pra|sobre|do|da|no|na|de)\s+"
                         r"(?:o |a )?(?:projeto\s+)?(?P<topic>.+)$")),
    ("dependents", re.compile(r"\b(quais|que)\s+(tarefas|registros|itens)?\s*dependem\s+(?:de|do|da|dessa|desta|"
                              r"deste|desse)?\s*(?:tarefa\s+)?(?P<topic>.+)$")),
    ("decisions", re.compile(r"\b(o que|que)\s+(eu\s+)?(havia|tinha|ja)?\s*decid\w*\s+(sobre|para|quanto a|"
                             r"a respeito d[oae])\s+(?:o |a )?(?P<topic>.+)$|\bdecis(ao|oes)\s+sobre\s+"
                             r"(?:o |a )?(?P<topic2>.+)$")),
    ("projects", re.compile(r"\b(quais|meus)\s+(sao\s+)?(meus\s+)?projetos( ativos)?\b")),
    ("upcoming", re.compile(r"\b(proximos|meus)\s+(compromissos|lembretes|eventos)\b|\bagenda da semana\b|"
                            r"\bo que tenho amanha\b|\bcompromissos de amanha\b")),
    ("review", re.compile(r"\b(o que|quais)\b.*\b(inferid\w*|capturad\w* automaticamente|preciso revisar)\b")),
    ("search", re.compile(r"\b(o que (eu )?(anotei|registrei|salvei|guardei)|procure|busque|pesquise|encontre)\s+"
                          r"(?:na memoria |nas notas |no segundo cerebro |nos registros )?(?:sobre |por |de |do |da )?"
                          r"(?P<topic>.+)$")),
)


def classify(text: str) -> tuple[str, str] | None:
    """(tipo de pergunta, assunto) — None quando não é uma pergunta ao Second Brain."""
    raw = " ".join(str(text or "").split())
    folded = parsing.fold(raw)
    for kind, pattern in QUESTION_PATTERNS:
        match = pattern.search(folded)
        if match:
            topic = ""
            for group in ("topic", "topic2"):
                if group in pattern.groupindex and match.group(group):
                    start, end = match.span(group)
                    topic = raw[start:end].strip(" ?.!,;:")
                    break
            return kind, topic
    return None


def answer(service: SecondBrainService, text: str) -> Answer:
    now = service.now_wall()
    found = classify(text)
    kind, topic = found if found else ("search", text)
    try:
        if kind == "today":
            day = service.today()
            parts = []
            if day["events"]:
                parts.append("Compromissos de hoje: " + _items(day["events"], now))
            if day["priorities"]:
                parts.append("Prioridades: " + _items(day["priorities"], now))
            if day["overdue"]:
                parts.append(f"{len(day['overdue'])} atrasado(s)")
            if not parts:
                return Answer("Não há compromissos nem tarefas prioritárias registrados para hoje.", [], "empty", kind)
            return Answer(". ".join(parts) + ".", day["events"] + day["priorities"], "list", kind)
        if kind == "week":
            records = service.week_open()
            if not records:
                return Answer("Não há tarefas abertas com prazo até o fim desta semana.", [], "empty", kind)
            return Answer(f"Para terminar até domingo ({len(records)}): {_items(records, now)}.", records, "list", kind)
        if kind == "overdue":
            records = service.overdue()
            if not records:
                return Answer("Nada atrasado.", [], "empty", kind)
            return Answer(f"Atrasado ({len(records)}): {_items(records, now)}.", records, "list", kind)
        if kind == "ideas":
            project, ideas = service.ideas_for(topic)
            name = project.title if project else topic
            if not ideas:
                return Answer(f"Não encontrei ideias salvas para {name}.", [], "empty", kind)
            return Answer(f"Ideias para {name} ({len(ideas)}): {_items(ideas, now)}.", ideas, "list", kind)
        if kind == "dependents":
            target = service.resolve(topic, open_only=False)
            records = service.dependents(target.id)
            if not records:
                return Answer(f"Nenhum registro depende de \"{target.title}\".", [], "empty", kind)
            return Answer(f"Dependem de \"{target.title}\": {_items(records, now)}.", records, "list", kind)
        if kind == "decisions":
            records = service.decisions_about(topic)
            if not records:
                return Answer(f"Não encontrei decisões registradas sobre {topic}.", [], "empty", kind)
            lines = [f"{r.title}" + (f": {r.body[:160]}" if r.body else "") for r in records[:5]]
            return Answer(f"Sobre {topic}: " + "; ".join(lines) + ".", records, "list", kind)
        if kind == "projects":
            projects = service.projects()
            if not projects:
                return Answer("Nenhum projeto ativo registrado.", [], "empty", kind)
            lines = [f"{p['record']['title']} ({p['open']} aberto(s))" for p in projects[:MAX_ITEMS]]
            return Answer("Projetos ativos: " + "; ".join(lines) + ".", [p["record"] for p in projects], "list", kind)
        if kind == "upcoming":
            tomorrow = bool(re.search(r"\bamanha\b", parsing.fold(text)))
            items = service.timeline(days=1, offset_days=1) if tomorrow else service.timeline(days=7)
            label = "Amanhã" if tomorrow else "Próximos 7 dias"
            if not items:
                return Answer("Nada agendado para amanhã." if tomorrow else "Nada agendado para os próximos 7 dias.",
                              [], "empty", kind)
            lines = []
            for item in items[:MAX_ITEMS]:
                if item["kind"] == "record":
                    rec = item["record"]
                    lines.append(f"{rec['title']} — {timeutil.describe(timeutil.parse_wall(rec['due_local']), all_day=rec['all_day'], now=now)}")
                else:
                    rem = item["reminder"]
                    lines.append(f"lembrete: {rem['title']} — {rem['when_text']}")
            return Answer(f"{label}: " + "; ".join(lines) + ".", [i.get("record") or i.get("reminder")
                                                                         for i in items], "list", kind)
        if kind == "review":
            records = service.review_queue()
            if not records:
                return Answer("Não há registros inferidos aguardando revisão.", [], "empty", kind)
            return Answer(f"Aguardando revisão ({len(records)}): {_items(records, now)}.", records, "list", kind)
        topic = topic or text
        records = service.search(topic, limit=20)
        if not records:
            return Answer(f"Não encontrei registros sobre \"{topic}\".", [], "empty", "search")
        groups: dict[str, list[Record]] = {}
        for record in records:
            groups.setdefault(record.kind, []).append(record)
        parts = [f"{KIND_PLURALS.get(k, KINDS.get(k, k))}: {_items(v, now, limit=4)}" for k, v in groups.items()]
        return Answer(f"Encontrei {len(records)} registro(s) sobre \"{topic}\". " + ". ".join(parts) + ".",
                      records, "list", "search")
    except NeedsClarification as exc:
        return Answer(exc.question, [], "clarify", kind)
    except SecondBrainError as exc:
        return Answer(str(exc), [], "empty", kind)
