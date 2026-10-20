"""CAPTURE — transforma frases em registros do Second Brain.

Dois caminhos, com regras diferentes:

* **explícito** ("anote essa ideia: …", "lembre-me de … amanhã às 18h", "nova tarefa: …"):
  o usuário pediu → o registro é CONFIRMADO;
* **automático** (frase comum com evidência clara de compromisso: "tenho dentista amanhã
  às 15h", "preciso entregar o relatório até sexta"): o usuário autorizou o registro de
  informações rotineiras e reversíveis, mas o resultado fica marcado como INFERIDO até ele
  confirmar na tela de revisão. Hipóteses ("talvez", "se der", "pensando em"), perguntas,
  frases sem data e qualquer dado sensível (senhas, tokens, autenticação, dados financeiros)
  NÃO são registrados automaticamente.

Data/hora ambígua nunca é chutada: a captura devolve a pergunta de esclarecimento e nada é
gravado. Com o modelo local disponível, ele pode resumir o título de uma captura automática
(inferência local, nunca serviço externo); sem ele, as regras bastam.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..memory.store import looks_secret
from . import parsing, timeutil
from .models import KINDS, Record
from .service import NeedsClarification, SecondBrainError, SecondBrainService, brief, describe_record

EVENT_WORDS = ("reuniao", "consulta", "prova", "aula", "entrevista", "compromisso", "dentista", "medico", "medica",
               "exame", "voo", "viagem", "jogo", "apresentacao", "palestra", "encontro", "almoco", "jantar",
               "aniversario", "festa", "call", "audiencia", "treino", "academia", "visita")
HYPOTHESIS_RE = re.compile(r"\b(talvez|quem sabe|se der|se eu|pode ser que|acho que vou|pensando em|estou pensando|"
                           r"to pensando|provavelmente|e se|seria bom|gostaria de|quem dera|sera que)\b")
FINANCIAL_RE = re.compile(r"(r\$\s*\d|\bus\$\s*\d|\b\d+[.,]\d{2}\s*(reais|dolares)\b|\bpix\b|\bagencia\s*\d|"
                          r"\bconta\s*(corrente|poupanca)?\s*\d{3,}|\bcartao\b.*\d{4}|\bboleto\s*\d{10,}|\biban\b|"
                          r"\bcnpj\b|\bcpf\b|\bsenha\b|\bcodigo de (seguranca|verificacao)\b|\btoken\b|\blogin\b)")
LEADING_RE = re.compile(
    r"^(?:(?:jarvis|ultron)[,:]?\s+)?(?:por favor[,]?\s+)?(?:"
    r"lembre-me|lembre me|me lembre|me lembra|lembra-me|me avise|me avisa|avise-me|anote|anota|registre|registra|"
    r"adicione|adiciona|crie|cria|marque|marca|agende|agenda|nova|novo|inclua|coloque|salve|guarde)\b"
    r"(?:\s+(?:que|de|do|da|para|pra|essa|esta|esse|este|uma|um|o|a|isso)\b)*[:,]?\s*", re.I)
KIND_PREFIX_RE = re.compile(r"^(?:a\s+|o\s+)?(ideia|nota|tarefa|compromisso|evento|reuniao|projeto|estudo|"
                            r"contato|pessoa|rotina|prazo|decisao|lembrete)\b(?:\s+(?:de|do|da|que|sobre|para))?[:,]?\s*",
                            re.I)
TRAILING_RE = re.compile(r"(?:\s+(?:ate|até|para|pra|as|às|a|à|no|na|em|de|do|da|dia|e|o|que|pelas|por volta))+\s*$",
                         re.I)
AUTO_EVENT_RE = re.compile(r"\b(?:eu\s+)?(?:tenho|terei|vou ter|marquei|tem)\s+(?:uma?\s+|o\s+|a\s+)?(" +
                           "|".join(EVENT_WORDS) + r")\b")
AUTO_TASK_RE = re.compile(r"\b(?:eu\s+)?(?:preciso|tenho que|tenho de|devo|vou)\s+(entregar|terminar|fazer|enviar|"
                          r"mandar|pagar|ligar|estudar|comprar|resolver|levar|buscar|revisar|finalizar|concluir|"
                          r"preparar|renovar|marcar|agendar|responder|retornar)\b")
FORGET_RE = re.compile(r"\bnao (?:posso|vou|devo) (?:me )?esquecer (?:de|que)\b")
PROJECT_RE = re.compile(r"\s*,?\s*\b(?:para|pro|pra|do|no|sobre)\s+(?:o\s+)?projeto\s+(?P<name>[^,.;:]{2,40}?)\s*"
                        r"(?=$|[,.;:])", re.I)

KIND_WORDS = {"ideia": "idea", "nota": "note", "tarefa": "task", "compromisso": "event", "evento": "event",
              "reuniao": "event", "projeto": "project", "estudo": "study", "contato": "person", "pessoa": "person",
              "rotina": "routine", "prazo": "deadline", "decisao": "note", "lembrete": "task"}


@dataclass
class CaptureResult:
    records: list = field(default_factory=list)
    question: str = ""                 # esclarecimento necessário (nada gravado)
    skipped: str = ""                  # motivo de não registrar (automático)
    inferred: bool = False
    pending: dict = field(default_factory=dict)   # o que falta para completar o registro (ver Capture.answer)
    reminder: Any = None                          # lembrete criado sobre um registro existente
    conflicts: list = field(default_factory=list)  # compromissos que se sobrepõem ao registrado (informados)

    @property
    def ok(self) -> bool:
        return bool(self.records)

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.to_dict() for r in self.records], "question": self.question,
                "skipped": self.skipped, "inferred": self.inferred, "pending": dict(self.pending),
                "reminder": self.reminder.to_dict() if self.reminder is not None else None,
                "conflicts": [brief(r) for r in self.conflicts]}


TITLE_QUESTIONS = {"idea": "Qual é a ideia?", "note": "O que devo anotar?", "task": "Qual é a tarefa?",
                   "event": "Qual é o compromisso?", "study": "O que você vai estudar?",
                   "deadline": "Qual é o prazo?", "project": "Qual é o nome do projeto?"}


def iso_when(value: Any) -> tuple[dt.datetime, bool] | None:
    """"2026-10-13 18:00" → (datetime, False); "2026-10-13" → (datetime 00:00, True); outro texto → None."""
    text = str(value or "").strip()
    try:
        return timeutil.parse_wall(text), False
    except (TypeError, ValueError):
        pass
    try:
        return dt.datetime.combine(dt.date.fromisoformat(text), dt.time(0, 0)), True
    except (TypeError, ValueError):
        return None


def _need(question: str) -> str:
    return "ampm" if question.startswith("Às ") else "datetime"


def sensitive(text: str) -> bool:
    """Senhas, tokens, autenticação e dados financeiros: nunca registrados automaticamente."""
    return looks_secret(text) or bool(FINANCIAL_RE.search(parsing.fold(text)))


def split_project(text: str) -> tuple[str, str | None]:
    """"ideia X para o projeto Atlas" → ("ideia X", "Atlas")."""
    match = PROJECT_RE.search(text)
    if not match:
        return text, None
    return (text[:match.start()] + text[match.end():]).strip(), match.group("name").strip()


def _when_value(parsed: parsing.When):
    """Prazo de dia inteiro vai como data (sem hora); com hora, como horário de parede."""
    if parsed.wall is None:
        return None
    return parsed.wall.date() if parsed.all_day else parsed.wall


def make_title(text: str, when: parsing.When | None) -> str:
    """Título limpo: sem comando, sem data/hora, sem preposição solta, com inicial maiúscula."""
    rest = when.strip(text) if when is not None else " ".join(str(text).split())
    rest = LEADING_RE.sub("", rest).strip()
    rest = KIND_PREFIX_RE.sub("", rest).strip()
    rest = re.sub(r"^(?:de|que|para|pra)\s+", "", rest, flags=re.I)
    previous = None
    while previous != rest:
        previous = rest
        rest = TRAILING_RE.sub("", rest).strip(" ,.;:-")
    rest = rest[:160].strip()
    return rest[:1].upper() + rest[1:] if rest else ""


def explicit_kind(text: str, default: str = "note") -> str:
    folded = parsing.fold(text)
    body = LEADING_RE.sub("", folded).strip()
    match = KIND_PREFIX_RE.match(body) or re.search(r"\b(ideia|tarefa|compromisso|reuniao|projeto|estudo|contato|"
                                                    r"rotina|prazo|decisao)\b", folded)
    if match:
        return KIND_WORDS.get(match.group(1).lower(), default)
    if re.search(r"\b(lembre-me|lembre me|me lembre|me lembra|lembra-me|me avise|avise-me)\b", folded):
        return "task"
    return default


class Capture:
    def __init__(self, service: SecondBrainService, *, settings_getter: Callable[[], Any] | None = None,
                 extractor: Callable[[str], str | None] | None = None):
        self.service = service
        self._settings = settings_getter or (lambda: None)
        self._extractor = extractor                  # título por inferência local (opcional)

    # ------------------------------------------------------------ explícito
    def explicit(self, text: str, *, kind: str | None = None, title: str | None = None, when: str | None = None,
                 priority: int | None = None, project: str | None = None, origin: str = "user",
                 remind: bool | None = None, leads: list | None = None, record_id: str | None = None,
                 body: str = "") -> CaptureResult:
        if looks_secret(text) or (title and looks_secret(title)) or (body and looks_secret(body)):
            raise SecondBrainError("o JARVIS não armazena senhas, tokens ou dados de autenticação")
        now = self.service.now_wall()
        resolved = iso_when(when) if when else None
        parsed = parsing.parse(text if resolved else (when if when else text), now)
        if resolved is not None:                       # data/hora já resolvida (resposta a um esclarecimento)
            parsed = parsing.When(wall=resolved[0], all_day=resolved[1], recurrence=parsed.recurrence,
                                  spans=parsed.spans, has_date=True, has_time=not resolved[1])
        kind = kind or explicit_kind(text)
        pending = {"mode": "explicit", "text": text[:600], "kind": kind, "title": title or "", "priority": priority,
                   "body": body or "",
                   "project": project or "", "remind": remind, "leads": list(leads or [])}
        if record_id:
            pending["record_id"] = record_id
        if parsed.ambiguous:
            return CaptureResult(question=parsed.ambiguous, pending={
                **pending, "need": _need(parsed.ambiguous), "question": parsed.ambiguous,
                "base": timeutil.format_wall(parsed.wall) if parsed.wall else ""})
        if record_id:
            return self._remind_existing(record_id, parsed, pending, now)
        folded = parsing.fold(text)
        is_reminder = bool(re.search(r"\b(lembre-me|lembre me|me lembre|me lembra|lembra-me|me avise|avise-me|"
                                     r"me avisa|lembrete)\b", folded))
        tags = ["decisão"] if re.search(r"\b(decisao|decidi|decidimos)\b", folded) else []
        body_text, project_name = split_project(text)
        project = project or project_name
        clean_title = title or make_title(body_text, parsing.parse(body_text, now) if (not when or resolved) else None)
        if not clean_title:
            question = TITLE_QUESTIONS.get(kind, "O que devo registrar?")
            return CaptureResult(question=question, pending={**pending, "need": "title", "question": question,
                                                            "when": when or ""})
        pending["title"] = clean_title
        if is_reminder and not parsed.has_time and not parsed.all_day and parsed.wall is None:
            question = "Para quando devo lembrar? Diga, por exemplo: amanhã às 18h."
            return CaptureResult(question=question, pending={**pending, "need": "datetime", "question": question,
                                                            "remind": True})
        if is_reminder and parsed.all_day and not parsed.has_time:
            question = f"A que horas devo lembrar {timeutil.describe(parsed.wall, all_day=True, now=now)}?"
            return CaptureResult(question=question, pending={**pending, "need": "time", "question": question,
                                                            "base": parsed.wall.date().isoformat(), "remind": True})
        if kind == "event" and parsed.wall is None:
            question = "Qual a data e o horário do compromisso?"
            return CaptureResult(question=question, pending={**pending, "need": "datetime", "question": question})
        record = self.service.create(
            kind, clean_title, body=body or "", when=_when_value(parsed),
            priority=priority or (3 if kind == "deadline" else 2),
            project=project, tags=tags, origin=origin, origin_detail=text[:300], confirmed=True,
            remind=(leads if leads else True) if (is_reminder or remind) else None, recurrence=parsed.recurrence)
        return CaptureResult(records=[record], conflicts=self.service.conflicts(record))

    # ------------------------------------------------------------ automático
    def auto(self, text: str, *, origin: str = "auto") -> CaptureResult:
        """Registra só com evidência clara de intenção, e sempre como inferência."""
        if not bool(getattr(self._settings(), "auto_capture", True)):
            return CaptureResult(skipped="captura automática desativada")
        clean = " ".join(str(text or "").split())
        folded = parsing.fold(clean)
        if not clean or clean.endswith("?") or len(clean) > 400:
            return CaptureResult(skipped="sem compromisso declarado")
        if sensitive(clean):
            return CaptureResult(skipped="conteúdo sensível não é registrado automaticamente")
        if HYPOTHESIS_RE.search(folded):
            return CaptureResult(skipped="hipótese não vira compromisso")
        event = AUTO_EVENT_RE.search(folded)
        task = AUTO_TASK_RE.search(folded)
        forget = FORGET_RE.search(folded)
        if not (event or task or forget):
            return CaptureResult(skipped="sem compromisso declarado")
        parsed = parsing.parse(clean, self.service.now_wall())
        if parsed.ambiguous:                                       # ambíguo: pergunta, não registra
            kind = "event" if event else "task"
            title = self._auto_title(clean, parsed)
            if not title:
                return CaptureResult(skipped="não foi possível extrair um título claro")
            return CaptureResult(question=f"{title}: {parsed.ambiguous[:1].lower()}{parsed.ambiguous[1:]}", pending={
                "mode": "auto", "text": clean[:600], "kind": kind, "title": title, "priority": None, "project": "",
                "remind": True if kind == "event" else None, "leads": [], "need": _need(parsed.ambiguous),
                "question": parsed.ambiguous, "base": timeutil.format_wall(parsed.wall) if parsed.wall else ""})
        if event and parsed.wall is None:
            return CaptureResult(skipped="compromisso sem data: perguntar antes de registrar")
        if (task and not forget) and parsed.wall is None:
            return CaptureResult(skipped="tarefa sem prazo: não registrada automaticamente")
        kind = "event" if event and parsed.has_time else ("task" if (task or forget or event) else "note")
        title = self._auto_title(clean, parsed)
        if not title:
            return CaptureResult(skipped="não foi possível extrair um título claro")
        duplicate = self._duplicate(kind, title, parsed.wall)
        if duplicate is not None:
            return CaptureResult(records=[duplicate], skipped="já registrado")
        record = self.service.create(kind, title, when=_when_value(parsed), origin=origin, origin_detail=clean[:300],
                                     confirmed=False, confidence=0.6,
                                     remind=True if kind == "event" else None, recurrence=parsed.recurrence)
        return CaptureResult(records=[record], inferred=True, conflicts=self.service.conflicts(record))

    def _remind_existing(self, record_id: str, parsed: parsing.When, pending: dict, now: dt.datetime) -> CaptureResult:
        """"Lembre-me disso amanhã às 18h" sobre um registro que já existe: lembrete com horário próprio."""
        target = self.service.get(record_id)
        if target is None or target.deleted_at:
            raise SecondBrainError("o registro citado não existe mais")
        pending = {**pending, "title": target.title, "remind": True}
        if parsed.wall is None:
            question = f"Quando devo lembrar de \"{target.title}\"?"
            return CaptureResult(question=question, pending={**pending, "need": "datetime", "question": question})
        if parsed.all_day or not parsed.has_time:
            question = f"A que horas devo lembrar {timeutil.describe(parsed.wall, all_day=True, now=now)}?"
            return CaptureResult(question=question, pending={**pending, "need": "time", "question": question,
                                                            "base": parsed.wall.date().isoformat()})
        if self.service.reminders is None:
            raise SecondBrainError("agendador de lembretes indisponível")
        reminder = self.service.reminders.schedule(target, at=parsed.wall, leads=[], recurrence=parsed.recurrence,
                                                   pinned=True)
        self.service.publish_summary()
        return CaptureResult(records=[target], reminder=reminder)

    def _auto_title(self, clean: str, parsed: parsing.When) -> str:
        title = make_title(clean, parsed)
        title = re.sub(r"^(?:eu\s+)?(?:tenho|terei|vou ter|marquei|preciso|tenho que|tenho de|devo|vou|"
                       r"nao (?:posso|vou|devo) (?:me )?esquecer (?:de|que)|não (?:posso|vou|devo) (?:me )?"
                       r"esquecer (?:de|que))\s+", "", title, flags=re.I).strip()
        if self._extractor is not None:
            try:
                better = self._extractor(clean)
                if better and not sensitive(better) and 2 <= len(better) <= 120:
                    title = better
            except Exception:
                pass
        return title[:1].upper() + title[1:] if title else ""

    # ------------------------------------------------------------ esclarecimento
    def answer(self, pending: dict, reply: str) -> CaptureResult | dict:
        """Completa um registro pendente com a resposta do usuário.

        Devolve os argumentos para ``secondbrain.capture`` (dict) ou um ``CaptureResult`` com nova
        pergunta. Nada é gravado aqui: o registro passa pelo Execution Engine como qualquer outro.
        """
        reply = " ".join(str(reply or "").split())
        if looks_secret(reply):
            raise SecondBrainError("o JARVIS não armazena senhas, tokens ou dados de autenticação")
        now = self.service.now_wall()
        need = pending.get("need", "datetime")
        args = {"text": pending.get("text") or reply, "kind": pending.get("kind") or None,
                "title": pending.get("title") or None, "priority": pending.get("priority"),
                "project": pending.get("project") or None, "remind": pending.get("remind"),
                "leads": pending.get("leads") or None, "record": pending.get("record_id") or None,
                "body": pending.get("body") or None}
        if need == "title":
            args.update(text=reply, title=None, when=pending.get("when") or None)
            return {k: v for k, v in args.items() if v not in (None, "", [])}
        folded = parsing.fold(reply)
        answer = parsing.parse(reply, now)
        wall: dt.datetime | None = None
        all_day = False
        if need == "ampm" and pending.get("base"):
            base = timeutil.parse_wall(pending["base"])
            h = base.hour
            if re.search(r"\b(tarde|noite)\b", folded) or re.search(rf"\b{h + 12}\b", folded):
                wall = base.replace(hour=h + 12)
            elif re.search(r"\b(manha|madrugada|cedo)\b", folded) or re.fullmatch(rf"(?:as\s+)?{h}(?:h|\s*horas?)?", folded):
                wall = base
            elif answer.has_time and answer.wall is not None and not answer.ambiguous:
                wall = base.replace(hour=answer.wall.hour, minute=answer.wall.minute)
        elif need == "time" and pending.get("base"):
            if answer.has_time and answer.wall is not None and not answer.ambiguous:
                day = dt.date.fromisoformat(pending["base"])
                wall = dt.datetime.combine(day, dt.time(answer.wall.hour, answer.wall.minute))
        else:
            if answer.wall is not None and not answer.ambiguous:
                wall, all_day = answer.wall, answer.all_day
                if all_day and pending.get("remind"):          # lembrete precisa de hora
                    question = f"A que horas devo lembrar {timeutil.describe(wall, all_day=True, now=now)}?"
                    return CaptureResult(question=question, pending={**pending, "need": "time", "question": question,
                                                                    "base": wall.date().isoformat()})
            elif answer.ambiguous:
                return CaptureResult(question=answer.ambiguous, pending={
                    **pending, "need": _need(answer.ambiguous), "question": answer.ambiguous,
                    "base": timeutil.format_wall(answer.wall) if answer.wall else ""})
        if wall is None:
            question = pending.get("question") or "Não entendi a data ou o horário. Pode repetir?"
            return CaptureResult(question=question, pending=dict(pending))
        if not all_day and wall < now - dt.timedelta(minutes=1):
            question = "Esse horário já passou. Para quando?"
            return CaptureResult(question=question, pending={**pending, "need": "datetime", "question": question})
        args["when"] = wall.date().isoformat() if all_day else timeutil.format_wall(wall)
        return {k: v for k, v in args.items() if v not in (None, "", [])}

    def _duplicate(self, kind: str, title: str, wall: dt.datetime | None) -> Record | None:
        """A mesma frase repetida não cria registros duplicados."""
        for record in self.service.search(title, kinds=(kind,), include_done=False, limit=5):
            same_title = parsing.fold(record.title) == parsing.fold(title)
            same_time = (wall is None and not record.due_local) or (
                wall is not None and record.due_local == timeutil.format_wall(wall))
            if same_title and same_time:
                return record
        return None


def confirmation_text(result: CaptureResult, *, now: dt.datetime | None = None) -> str:
    """Resposta curta e verdadeira sobre o que foi (ou não) gravado."""
    if result.question:
        return result.question
    if not result.records:
        return "Nada foi registrado."
    record = result.records[0]
    if result.reminder is not None:
        when = timeutil.describe(timeutil.parse_wall(result.reminder.at_local), now=now)
        return f"Lembrete criado: {record.title} — {when}."
    label = KINDS.get(record.kind, "Registro")
    verb = "registrada" if label in ("Tarefa", "Ideia", "Nota", "Pessoa", "Rotina") else "registrado"
    text = f"{label} {verb}: {describe_record(record, now=now)}."
    if result.inferred:
        text += " Marcado como inferido; confirme ou corrija em Revisão."
    if result.skipped == "já registrado":
        text = f"{label} já estava registrado: {describe_record(record, now=now)}."
    if result.conflicts:
        names = "; ".join(describe_record(r, now=now) for r in result.conflicts[:3])
        more = f" e mais {len(result.conflicts) - 3}" if len(result.conflicts) > 3 else ""
        text += f" Atenção: conflita com {names}{more}."
    return text


__all__ = ["Capture", "CaptureResult", "NeedsClarification", "confirmation_text", "make_title", "sensitive"]
