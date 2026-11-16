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
from .models import KIND_PLURALS, KINDS, RELATIONS as RELATION_LABELS, Record
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
    ("between", re.compile(r"\brelac(?:ao|oes)\s+entre\s+(?:o |a )?(?:projeto\s+)?(?P<topic>.+?)\s+e\s+"
                           r"(?:o |a )?(?:projeto\s+)?(?P<topic2>.+)$")),
    ("related", re.compile(r"\b(?:projetos|registros|itens|notas|ideias|tarefas|coisas)\s+(?:estao\s+|sao\s+|esta\s+)?"
                           r"(?:relacionad\w*|ligad\w*|conectad\w*)\s+(?:a|ao|aos|as|com)\s+(?:o |a )?(?:projeto\s+)?"
                           r"(?P<topic>.+)$|\bo que (?:se )?(?:relaciona|liga|conecta)\s+(?:a|ao|com)\s+(?:o |a )?"
                           r"(?:projeto\s+)?(?P<topic2>.+)$")),
    ("decisions_all", re.compile(r"^(?:jarvis,?\s+)?(?:quais|que|minhas|liste|mostre|me mostre)\s+(?:sao\s+)?(?:as\s+)?"
                                 r"(?:minhas\s+)?decisoes\b(?:\s+(?:que\s+)?(?:eu\s+)?(?:tomei|registrei|anotei|salvei))?"
                                 r"\s*[?.!]*$")),
    ("listing", re.compile(r"^(?:jarvis,?\s+)?(?:quais|que|minhas|meus|liste|listar|lista|mostre|mostra|me mostre)\s+"
                           r"(?:sao\s+)?(?:as\s+|os\s+)?(?:minhas\s+|meus\s+)?(?P<kind>ideias|notas|anotacoes|tarefas|"
                           r"estudos|prazos|rotinas|pessoas|compromissos)\b(?:\s+(?:que\s+)?(?:eu\s+)?(?:salvei|anotei|"
                           r"registrei|tenho|guardei|criei|salvas|registradas|pendentes|abertas))?\s*[?.!]*$")),
    ("projects", re.compile(r"\b(quais|meus)\s+(sao\s+)?(meus\s+)?projetos( ativos)?\b")),
    ("upcoming", re.compile(r"\b(proximos|meus)\s+(compromissos|lembretes|eventos)\b|\bagenda da semana\b|"
                            r"\bo que tenho amanha\b|\bcompromissos de amanha\b")),
    ("review", re.compile(r"\b(o que|quais)\b.*\b(inferid\w*|capturad\w* automaticamente|preciso revisar)\b")),
    ("search", re.compile(r"\b(o que (eu )?(anotei|registrei|salvei|guardei)|procure|busque|pesquise|encontre)\s+"
                          r"(?:na memoria |nas notas |no segundo cerebro |nos registros )?(?:sobre |por |de |do |da )?"
                          r"(?P<topic>.+)$")),
)


LISTING_KINDS = {"ideias": ("idea",), "notas": ("note",), "anotacoes": ("note",), "tarefas": ("task",),
                 "estudos": ("study",), "prazos": ("deadline",), "rotinas": ("routine",), "pessoas": ("person",),
                 "compromissos": ("event",)}


LISTING_LABELS = {"anotacoes": "anotações"}
FEMININE = {"ideias", "notas", "anotacoes", "tarefas", "rotinas", "pessoas"}


def _project_note(note: dict) -> str:
    project = f" [{note['project']}]" if note.get("project") else ""
    return f"{str(note.get('text') or '')[:160]}{project} (memória de projeto da TARDIS)"


def _relations(service: SecondBrainService, kind: str, topic: str, now: dt.datetime) -> Answer:
    """Relações de um projeto (ou entre dois), só com o que está salvo: ligações explícitas, itens do projeto,
    etiquetas em comum e citações."""
    names = [t.strip() for t in topic.split("|")] if kind == "between" else [topic]
    records = [service.resolve(name, kinds=("project",)) if _has_project(service, name) else service.resolve(name)
               for name in names]
    if kind == "between":
        a, b = records
        found = []
        for rel in service.related(a.id):
            if rel["record"]["id"] == b.id:
                found.append(f"ligação registrada: {RELATION_LABELS.get(rel['type'], rel['type'])}")
        common = sorted({parsing.fold(t) for t in a.tags} & {parsing.fold(t) for t in b.tags})
        if common:
            found.append("etiquetas em comum: " + ", ".join(common))
        for x, y in ((a, b), (b, a)):
            if any(m.id == y.id for m in service.connections(x)["mentioned"]):
                found.append(f"\"{y.title}\" é citado nos registros de \"{x.title}\"")
        if not found:
            return Answer(f"Não encontrei relação registrada entre \"{a.title}\" e \"{b.title}\".", [], "empty", kind)
        return Answer(f"Entre \"{a.title}\" e \"{b.title}\": " + "; ".join(found) + ".", [a, b], "list", kind)
    record = records[0]
    links = service.connections(record)
    parts = []
    if links["explicit"]:
        parts.append("ligações registradas: " + "; ".join(
            f"{RELATION_LABELS.get(r['type'], r['type'])} \"{r['record']['title']}\"" for r in links["explicit"][:6]))
    if links["members"]:
        counts: dict[str, int] = {}
        for m in links["members"]:
            counts[m.kind] = counts.get(m.kind, 0) + 1
        parts.append("itens do projeto: " + ", ".join(f"{n} {KIND_PLURALS.get(k, k).lower()}"
                                                      for k, n in counts.items()))
    if links["shared_tags"]:
        parts.append("projetos com etiquetas em comum: " + "; ".join(
            f"\"{s['record'].title}\" ({', '.join(s['tags'])})" for s in links["shared_tags"][:5]))
    if links["mentioned"]:
        parts.append("projetos citados nos registros: " + ", ".join(f"\"{m.title}\"" for m in links["mentioned"][:5]))
    if not parts:
        return Answer(f"Não encontrei relações registradas para \"{record.title}\".", [record], "empty", kind)
    return Answer(f"\"{record.title}\" — " + ". ".join(parts) + ".", [record], "list", kind)


def _has_project(service: SecondBrainService, name: str) -> bool:
    try:
        service.resolve(name, kinds=("project",))
        return True
    except (SecondBrainError, NeedsClarification):
        return False


def classify(text: str) -> tuple[str, str] | None:
    """(tipo de pergunta, assunto) — None quando não é uma pergunta ao Second Brain."""
    raw = " ".join(str(text or "").split())
    folded = parsing.fold(raw)
    for kind, pattern in QUESTION_PATTERNS:
        match = pattern.search(folded)
        if match:
            topic = ""
            if kind == "between":
                spans = [match.span(g) for g in ("topic", "topic2")]
                return kind, " | ".join(raw[a:b].strip(" ?.!,;:") for a, b in spans)
            if kind == "listing":
                return kind, match.group("kind")
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
            tardis = service.project_decisions(topic, limit=5)
            if not records and not tardis:
                return Answer(f"Não encontrei decisões registradas sobre {topic}.", [], "empty", kind)
            lines = [f"{r.title}" + (f": {r.body[:160]}" if r.body else "") for r in records[:5]]
            lines += [_project_note(n) for n in tardis]
            return Answer(f"Sobre {topic}: " + "; ".join(lines) + ".", records + tardis, "list", kind)
        if kind == "decisions_all":
            records = service.decisions(limit=MAX_ITEMS)
            tardis = service.project_decisions(limit=MAX_ITEMS)
            if not records and not tardis:
                return Answer("Não há decisões registradas na memória.", [], "empty", kind)
            lines = [r.title + (f": {r.body[:120]}" if r.body else "") for r in records]
            lines += [_project_note(n) for n in tardis]
            total = len(records) + len(tardis)
            return Answer(f"Decisões registradas ({total}): " + "; ".join(lines[:MAX_ITEMS]) +
                          (f" (e mais {total - MAX_ITEMS})" if total > MAX_ITEMS else "") + ".",
                          records + tardis, "list", kind)
        if kind == "listing":
            wanted = LISTING_KINDS.get(parsing.fold(topic), ())
            status = ("open", "in_progress", "waiting") if set(wanted) & {"task", "study", "deadline", "event"} else None
            records = service.list(kinds=wanted, status=status, order="smart" if status else "recent", limit=200)
            key = parsing.fold(topic)
            label = LISTING_LABELS.get(key, topic.lower())
            if not records:
                ending = "registradas" if key in FEMININE else "registrados"
                return Answer(f"Não há {label} {ending} na memória.", [], "empty", kind)
            return Answer(f"{label.capitalize()} ({len(records)}): {_items(records, now)}.", records, "list", kind)
        if kind in ("related", "between"):
            return _relations(service, kind, topic, now)
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
