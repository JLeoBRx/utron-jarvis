"""SECOND BRAIN — o serviço único das memórias pessoais do usuário.

A interface (HUB 2), a voz e o texto chamam ESTE serviço (via skills, que passam pela camada
central de autonomia e auditoria). Não existe banco nem regra de negócio paralela por canal.

* registros persistentes (tarefas, compromissos, estudos, projetos, ideias, notas, pessoas,
  rotinas, prazos) com histórico de mudanças, relações, lixeira recuperável e exclusão
  definitiva;
* fatos confirmados × inferências: o que foi capturado automaticamente fica marcado como
  inferido até o usuário confirmar na tela de revisão — nunca vira compromisso confirmado
  sozinho;
* senhas, tokens e dados financeiros/autenticação são recusados antes de qualquer gravação;
* cada mudança publica um evento com o registro completo: os dois hubs se atualizam pelo
  evento, sem reconsultar o banco inteiro; o resumo vai para o JARVIS_STATE.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
import uuid
from typing import Any, Callable, Iterable

from ..core.events import EventType
from ..memory.store import clean_text, looks_secret
from . import parsing, timeutil
from .models import ACTIONABLE, KINDS, PRIORITIES, RELATIONS, STATUSES, Record
from .store import SecondBrainStore

log = logging.getLogger("ultron.secondbrain")

EDITABLE = ("title", "body", "kind", "status", "priority", "due_local", "all_day", "end_local", "recurrence",
            "project_id", "tags", "confirmed", "data")
GRAPH_TYPES = {"idea": "IDEA", "project": "PROJECT", "note": "MEMORY", "person": "CONCEPT", "study": "CONCEPT"}
DEFAULT_EVENT_MINUTES = 60      # compromisso sem horário de término ocupa 1 h na checagem de conflitos
EXPORT_FORMATS = ("json", "csv")


CONTEXT_PROJECT_RE = re.compile(r"(?:(?:esse|este|desse|deste|nesse|neste|aquele|o|meu|do|no)\s+)?projeto|"
                                r"(?:esse|este|ele|isso)")


class SecondBrainError(ValueError):
    """Erro com mensagem pronta para o usuário."""


class NeedsClarification(SecondBrainError):
    """A frase é ambígua (data, hora ou registro): a pergunta vai para o usuário."""

    def __init__(self, question: str, candidates: list | None = None):
        super().__init__(question)
        self.question = question
        self.candidates = list(candidates or [])


class SecondBrainService:
    name = "second_brain"

    def __init__(self, db, *, bus=None, state=None, settings_getter: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.time, graph=None):
        self.store = SecondBrainStore(db)
        self.db = db
        self._bus = bus
        self._state = state
        self._settings = settings_getter or (lambda: None)
        self._clock = clock
        self._graph = graph
        self._lock = threading.RLock()
        self.reminders = None                     # ReminderScheduler (ligado pelo Neural Core)

    # ================================================================ ciclo de vida
    def start(self) -> None:
        self.store.ensure_fts()
        self.publish_summary()

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        summary = self.summary()
        detail = (f"{summary['open_tasks']} tarefa(s) aberta(s), {summary['overdue']} atrasada(s); "
                  f"busca {'FTS5' if self.store.fts else 'texto normalizado'}")
        return {"status": "OK", "detail": detail}

    # ================================================================ utilidades
    @property
    def tz(self) -> str:
        return str(getattr(self._settings(), "timezone", "") or "")

    def now(self) -> float:
        return self._clock()

    def now_wall(self) -> dt.datetime:
        return timeutil.from_epoch(self._clock(), self.tz)

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="second_brain")

    @staticmethod
    def _new_id() -> str:
        return "r_" + uuid.uuid4().hex[:12]

    @staticmethod
    def _clean(value: Any, limit: int, *, field: str, allow_empty: bool = False) -> str:
        try:
            return clean_text(value, limit, field=field, allow_empty=allow_empty)
        except ValueError as exc:
            raise SecondBrainError(str(exc)) from exc

    def _resolve_when(self, when: Any, *, kind: str) -> tuple[str, float | None, bool, str]:
        """(horário de parede, epoch, dia inteiro, recorrência) a partir de texto, datetime ou parede."""
        if when in (None, ""):
            return "", None, False, ""
        if isinstance(when, dt.datetime):
            wall, all_day, recurrence = when.replace(second=0, microsecond=0, tzinfo=None), False, ""
        elif isinstance(when, dt.date):
            wall, all_day, recurrence = dt.datetime.combine(when, dt.time(0, 0)), True, ""
        else:
            text = str(when).strip()
            try:
                wall, all_day, recurrence = timeutil.parse_wall(text), False, ""
            except ValueError:
                parsed = parsing.parse(text, self.now_wall())
                if parsed.ambiguous:
                    raise NeedsClarification(parsed.ambiguous)
                if parsed.wall is None:
                    raise NeedsClarification(f"Não entendi a data \"{text}\". Diga, por exemplo: amanhã às 18h.")
                wall, all_day, recurrence = parsed.wall, parsed.all_day, parsed.recurrence
        return timeutil.format_wall(wall), timeutil.to_epoch(wall, self.tz), all_day, recurrence

    # ================================================================ escrita
    def create(self, kind: str, title: str, *, body: str = "", when: Any = None, priority: int = 2,
               project: str | None = None, tags: Iterable[str] = (), origin: str = "user", origin_detail: str = "",
               confirmed: bool = True, confidence: float = 1.0, data: dict | None = None,
               remind: bool | list | None = None, recurrence: str = "", end: Any = None) -> Record:
        kind = str(kind or "note").lower()
        if kind not in KINDS:
            raise SecondBrainError(f"categoria desconhecida: {kind}")
        title = self._clean(title, 200, field="título")
        body = self._clean(body, 4000, field="descrição", allow_empty=True)
        tags = [self._clean(t, 40, field="etiqueta") for t in tags if str(t).strip()][:12]
        if looks_secret(origin_detail):
            origin_detail = ""
        due_local, due_at, all_day, parsed_recurrence = self._resolve_when(when, kind=kind)
        recurrence = recurrence or parsed_recurrence
        if recurrence not in timeutil.RECURRENCES:
            raise SecondBrainError(f"recorrência inválida: {recurrence}")
        end_local = self._resolve_when(end, kind=kind)[0] if end else ""
        project_id = self._project_id(project, origin=origin) if project else None
        now = self.now()
        record = Record(self._new_id(), kind, title, body, "open", max(1, min(4, int(priority))), due_local, due_at,
                        all_day, end_local, self.tz, recurrence, project_id, tags, origin, origin_detail[:300],
                        bool(confirmed), max(0.0, min(1.0, float(confidence))), dict(data or {}), now, now)
        with self._lock:
            self.store.insert(record)
            self.store.log(record.id, "created", {"title": title, "kind": kind, "due": due_local,
                                                  "confirmed": bool(confirmed)}, origin)
        self._link_graph(record)
        reminder = None
        if self.reminders is not None and due_at is not None and (remind or (remind is None and kind == "event")):
            leads = remind if isinstance(remind, list) else self._default_leads(kind, all_day)
            reminder = self.reminders.schedule(record, leads=leads)
        conflicts = [brief(r) for r in self.conflicts(record)] if kind == "event" else []
        self._emit(EventType.RECORD_CREATED, record=record.to_dict(), change="created",
                   reminder=reminder.to_dict() if reminder else None, conflicts=conflicts)
        self.publish_summary()
        return record

    def _default_leads(self, kind: str, all_day: bool) -> list[int]:
        if kind != "event" or all_day:
            return []
        values = getattr(self._settings(), "reminder_default_leads", ("10",)) or ()
        leads = []
        for value in values:
            try:
                minutes = int(float(value))
            except (TypeError, ValueError):
                continue
            if 0 < minutes <= 43200:
                leads.append(minutes)
        return sorted(set(leads), reverse=True)

    def _project_id(self, project: str, *, origin: str) -> str:
        existing = self.store.get(project)
        if existing is not None and existing.kind == "project":
            return existing.id
        matches = [r for r in self.search(project, kinds=("project",), limit=5) if r.is_open]
        exact = [r for r in matches if parsing.fold(r.title) == parsing.fold(project)]
        if exact or len(matches) == 1:
            return (exact or matches)[0].id
        return self.create("project", project, origin=origin).id         # projeto novo, registrado na hora

    def update(self, record_id: str, *, origin: str = "user", when: Any = "__keep__", **changes: Any) -> Record:
        with self._lock:
            record = self._require(record_id)
            before = record.to_dict()
            if when != "__keep__":
                due_local, due_at, all_day, recurrence = self._resolve_when(when, kind=changes.get("kind", record.kind))
                record.due_local, record.due_at, record.all_day = due_local, due_at, all_day
                if recurrence:
                    record.recurrence = recurrence
            for key, value in changes.items():
                if key not in EDITABLE:
                    raise SecondBrainError(f"campo não editável: {key}")
                if key == "title":
                    value = self._clean(value, 200, field="título")
                elif key == "body":
                    value = self._clean(value, 4000, field="descrição", allow_empty=True)
                elif key == "kind" and value not in KINDS:
                    raise SecondBrainError(f"categoria desconhecida: {value}")
                elif key == "status" and value not in STATUSES:
                    raise SecondBrainError(f"estado inválido: {value}")
                elif key == "priority":
                    value = max(1, min(4, int(value)))
                elif key == "tags":
                    value = [self._clean(t, 40, field="etiqueta") for t in value if str(t).strip()][:12]
                elif key == "due_local":
                    value, record.due_at, record.all_day, _r = self._resolve_when(value, kind=record.kind) \
                        if value else ("", None, False, "")
                elif key == "project_id" and value:
                    value = self._project_id(value, origin=origin)
                elif key == "recurrence" and value not in timeutil.RECURRENCES:
                    raise SecondBrainError(f"recorrência inválida: {value}")
                setattr(record, key, value)
            if record.status == "done" and not record.completed_at:
                record.completed_at = self.now()
            elif record.status != "done":
                record.completed_at = None
            after = record.to_dict()
            diff = {k: [before[k], after[k]] for k in EDITABLE + ("due_at",)
                    if before.get(k) != after.get(k) and k in after}
            if not diff:
                return record
            record.updated_at = self.now()
            self.store.save(record)
            self.store.log(record.id, "updated", diff, origin)
        if self.reminders is not None and ("due_local" in diff or "due_at" in diff or "recurrence" in diff):
            self.reminders.reschedule_record(record)
        if "status" in diff and record.status in ("done", "cancelled") and self.reminders is not None:
            self.reminders.finish_record(record)
        conflicts = [brief(r) for r in self.conflicts(record)] \
            if record.kind == "event" and {"due_local", "due_at", "end_local", "status"} & set(diff) else []
        self._emit(EventType.RECORD_UPDATED, record=record.to_dict(), change="edited", fields=sorted(diff),
                   conflicts=conflicts)
        self.publish_summary()
        return record

    def complete(self, record_id: str, *, origin: str = "user") -> Record:
        with self._lock:
            record = self._require(record_id)
            if record.recurrence and record.due_local:
                current = timeutil.parse_wall(record.due_local)
                nxt = timeutil.next_occurrence(current, record.recurrence, after=max(current, self.now_wall()))
                if nxt is not None:
                    before = record.due_local
                    record.due_local = timeutil.format_wall(nxt)
                    record.due_at = timeutil.to_epoch(nxt, record.tz or self.tz)
                    record.updated_at = self.now()
                    self.store.save(record)
                    self.store.log(record.id, "completed_occurrence", {"due": [before, record.due_local]}, origin)
                    if self.reminders is not None:
                        self.reminders.reschedule_record(record)
                    self._emit(EventType.RECORD_UPDATED, record=record.to_dict(), change="completed_occurrence")
                    self.publish_summary()
                    return record
            if record.status == "done":
                return record
            record.status, record.completed_at, record.updated_at = "done", self.now(), self.now()
            self.store.save(record)
            self.store.log(record.id, "completed", {"status": ["open", "done"]}, origin)
        if self.reminders is not None:
            self.reminders.finish_record(record)
        self._emit(EventType.RECORD_UPDATED, record=record.to_dict(), change="completed")
        self.publish_summary()
        return record

    def reopen(self, record_id: str, *, origin: str = "user") -> Record:
        return self.update(record_id, origin=origin, status="open")

    def confirm(self, record_id: str, *, origin: str = "user") -> Record:
        """Revisão: o usuário confirma uma inferência (captura automática)."""
        return self.update(record_id, origin=origin, confirmed=True)

    def archive(self, record_id: str, *, archived: bool = True, origin: str = "user") -> Record:
        with self._lock:
            record = self._require(record_id)
            if bool(record.archived_at) == archived:
                return record
            record.archived_at = self.now() if archived else None
            record.updated_at = self.now()
            self.store.save(record)
            self.store.log(record.id, "archived" if archived else "unarchived", {}, origin)
        if archived and self.reminders is not None:
            self.reminders.finish_record(record, cancelled=True)
        self._emit(EventType.RECORD_UPDATED, record=record.to_dict(), change="archived" if archived else "unarchived")
        self.publish_summary()
        return record

    def delete(self, record_id: str, *, permanent: bool = False, origin: str = "user") -> dict:
        """Lixeira (recuperável) ou exclusão definitiva (irreversível — a skill exige autorização)."""
        with self._lock:
            record = self._require(record_id, include_deleted=True)
            snapshot = record.to_dict()
            if permanent:
                self.store.purge(record.id)
                if self._graph is not None and record.kind in GRAPH_TYPES:
                    try:
                        self._graph.remove_node(f"sb:{record.id}")
                    except Exception:
                        pass
            else:
                if record.deleted_at:
                    return {"record": snapshot, "permanent": False}
                record.deleted_at, record.updated_at = self.now(), self.now()
                self.store.save(record)
                self.store.log(record.id, "deleted", {}, origin)
        if self.reminders is not None and not permanent:
            self.reminders.finish_record(record, cancelled=True)
        try:
            self.db.audit("second_brain", "purge" if permanent else "trash", f"{record.kind} {record.id}", True)
        except Exception:
            pass
        self._emit(EventType.RECORD_DELETED, record=snapshot, permanent=permanent)
        self.publish_summary()
        return {"record": snapshot, "permanent": permanent}

    def restore(self, record_id: str, *, origin: str = "user") -> Record:
        with self._lock:
            record = self._require(record_id, include_deleted=True)
            if not record.deleted_at:
                return record
            record.deleted_at, record.updated_at = None, self.now()
            self.store.save(record)
            self.store.log(record.id, "restored", {}, origin)
        if self.reminders is not None:
            self.reminders.reschedule_record(record)
        self._emit(EventType.RECORD_RESTORED, record=record.to_dict())
        self.publish_summary()
        return record

    def trash(self, *, limit: int = 200) -> list[Record]:
        return self.store.select(["deleted_at IS NOT NULL"], order="deleted_at DESC", limit=limit)

    def empty_trash(self, *, origin: str = "user") -> int:
        removed = 0
        for record in self.trash(limit=10000):
            self.delete(record.id, permanent=True, origin=origin)
            removed += 1
        return removed

    # ================================================================ relações
    def relate(self, src: str, dst: str, type_: str = "related", *, origin: str = "user") -> bool:
        if type_ not in RELATIONS:
            raise SecondBrainError(f"relação inválida: {type_}")
        a, b = self._require(src), self._require(dst)
        if a.id == b.id:
            raise SecondBrainError("um registro não se relaciona consigo mesmo")
        if type_ == "depends_on" and self._depends_on(b.id, a.id):
            raise SecondBrainError("isso criaria uma dependência circular")
        created = self.store.relate(a.id, b.id, type_)
        if created:
            self.store.log(a.id, "related", {"to": b.id, "type": type_}, origin)
            self._emit(EventType.RECORD_UPDATED, record=a.to_dict(), change="related", related=b.id, type=type_)
        return created

    def _depends_on(self, src: str, target: str, seen: set | None = None) -> bool:
        seen = seen if seen is not None else set()
        if src in seen:
            return False
        seen.add(src)
        for nxt in self.store.related_ids(src, "depends_on", incoming=False):
            if nxt == target or self._depends_on(nxt, target, seen):
                return True
        return False

    def dependents(self, record_id: str) -> list[Record]:
        """Registros que dependem deste (ex.: tarefas bloqueadas por esta tarefa)."""
        ids = self.store.related_ids(record_id, "depends_on", incoming=True)
        return [r for r in (self.store.get(i) for i in ids) if r is not None and not r.deleted_at]

    def dependencies(self, record_id: str) -> list[Record]:
        ids = self.store.related_ids(record_id, "depends_on", incoming=False)
        return [r for r in (self.store.get(i) for i in ids) if r is not None and not r.deleted_at]

    def related(self, record_id: str) -> list[dict]:
        out = []
        for rel in self.store.relations(record_id):
            other_id = rel["dst"] if rel["src"] == record_id else rel["src"]
            other = self.store.get(other_id)
            if other is not None and not other.deleted_at:
                out.append({"type": rel["type"], "direction": "out" if rel["src"] == record_id else "in",
                            "record": other.to_dict()})
        return out

    # ================================================================ leitura
    def _require(self, record_id: str, *, include_deleted: bool = False) -> Record:
        record = self.store.get(record_id)
        if record is None or (record.deleted_at and not include_deleted):
            raise SecondBrainError("registro não encontrado")
        return record

    def get(self, record_id: str) -> Record | None:
        return self.store.get(record_id)

    def resolve(self, ref: str, *, kinds: Iterable[str] | None = None, open_only: bool = False) -> Record:
        """Registro por id ou pelo título (ex.: "a tarefa do relatório"). Ambíguo → pergunta."""
        ref = str(ref or "").strip()
        direct = self.store.get(ref) if ref.startswith("r_") else None
        if direct is not None and not direct.deleted_at:
            return direct
        candidates = [r for r in self.search(ref, kinds=kinds, limit=8) if not open_only or r.is_open]
        if not candidates:
            raise SecondBrainError(f"Não encontrei nenhum registro sobre \"{ref}\".")
        exact = [r for r in candidates if parsing.fold(r.title) == parsing.fold(ref)]
        if len(exact) == 1 or len(candidates) == 1:
            return (exact or candidates)[0]
        options = "; ".join(f"{i + 1}) {r.title}" + (f" ({timeutil.describe(timeutil.parse_wall(r.due_local), all_day=r.all_day, now=self.now_wall())})"
                                                       if r.due_local else "") for i, r in enumerate(candidates[:4]))
        raise NeedsClarification(f"Encontrei {len(candidates)} registros: {options}. Qual deles?",
                                 [r.id for r in candidates[:4]])

    def list(self, *, kinds: Iterable[str] | None = None, status: Iterable[str] | None = None,
             project: str | None = None, due_before: float | None = None, due_after: float | None = None,
             confirmed: bool | None = None, include_archived: bool = False, order: str = "smart",
             limit: int = 200) -> list[Record]:
        where, params = ["deleted_at IS NULL"], []
        if not include_archived:
            where.append("archived_at IS NULL")
        if kinds:
            kinds = [k for k in kinds if k in KINDS]
            where.append(f"kind IN ({', '.join('?' for _ in kinds)})")
            params.extend(kinds)
        if status:
            status = [s for s in status if s in STATUSES]
            where.append(f"status IN ({', '.join('?' for _ in status)})")
            params.extend(status)
        if project:
            where.append("project_id = ?")
            params.append(project)
        if due_before is not None:
            where.append("due_at IS NOT NULL AND due_at < ?")
            params.append(due_before)
        if due_after is not None:
            where.append("due_at IS NOT NULL AND due_at >= ?")
            params.append(due_after)
        if confirmed is not None:
            where.append("confirmed = ?")
            params.append(int(confirmed))
        orders = {"smart": "CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, priority DESC, updated_at DESC",
                  "recent": "updated_at DESC", "created": "created_at DESC", "priority": "priority DESC, due_at",
                  "title": "title COLLATE NOCASE"}
        return self.store.select(where, params, order=orders.get(order, orders["smart"]), limit=limit)

    def search(self, text: str, *, kinds: Iterable[str] | None = None, include_done: bool = True,
               include_archived: bool = False, project: str | None = None, limit: int = 50) -> list[Record]:
        ids = self.store.search_ids(text, limit=max(limit * 4, 50))
        out = []
        kinds = set(kinds or ())
        for record_id in ids:
            record = self.store.get(record_id)
            if record is None or record.deleted_at or (record.archived_at and not include_archived):
                continue
            if kinds and record.kind not in kinds:
                continue
            if not include_done and record.status in ("done", "cancelled"):
                continue
            if project and record.project_id != project:
                continue
            out.append(record)
            if len(out) >= limit:
                break
        return out

    def _day_bounds(self, offset_days: int = 0) -> tuple[float, float]:
        today = self.now_wall().date() + dt.timedelta(days=offset_days)
        start = timeutil.to_epoch(dt.datetime.combine(today, dt.time(0, 0)), self.tz)
        end = timeutil.to_epoch(dt.datetime.combine(today + dt.timedelta(days=1), dt.time(0, 0)), self.tz)
        return start, end

    def overdue(self, *, limit: int = 100) -> list[Record]:
        now = self.now()
        candidates = self.list(kinds=ACTIONABLE, status=("open", "in_progress", "waiting"), due_before=now,
                               limit=limit * 2)
        return [r for r in candidates if r.overdue(now)][:limit]

    def due_between(self, start: float, end: float, *, kinds: Iterable[str] = ACTIONABLE,
                    open_only: bool = True) -> list[Record]:
        status = ("open", "in_progress", "waiting") if open_only else None
        return self.list(kinds=kinds, status=status, due_after=start, due_before=end)

    def week_open(self, *, kinds: Iterable[str] = ("task", "study", "deadline", "routine")) -> list[Record]:
        """O que ainda precisa ser terminado até o fim desta semana (domingo), incluindo atrasados."""
        today = self.now_wall().date()
        sunday = today + dt.timedelta(days=6 - today.weekday())
        end = timeutil.to_epoch(dt.datetime.combine(sunday + dt.timedelta(days=1), dt.time(0, 0)), self.tz)
        return self.list(kinds=kinds, status=("open", "in_progress", "waiting"), due_before=end)

    # ================================================================ conflitos de agenda
    def span(self, record: Record) -> tuple[float, float] | None:
        """(início, fim) de um compromisso com horário; None para dia inteiro ou sem data."""
        if record.due_at is None or record.all_day:
            return None
        start = float(record.due_at)
        if record.end_local:
            try:
                end = timeutil.to_epoch(timeutil.parse_wall(record.end_local), record.tz or self.tz)
            except ValueError:
                end = 0.0
            if end > start:
                return start, end
        return start, start + DEFAULT_EVENT_MINUTES * 60

    def conflicts(self, record: Record | str) -> list[Record]:
        """Compromissos abertos que se sobrepõem a este. Só compromissos com horário ocupam a agenda:
        tarefas e prazos não conflitam, e um dia inteiro não conflita com horários. Nada é bloqueado —
        o conflito é informado para o usuário decidir."""
        if isinstance(record, str):
            record = self._require(record)
        if record.kind != "event" or record.status not in ("open", "in_progress", "waiting") \
                or record.deleted_at or record.archived_at:
            return []
        span = self.span(record)
        if span is None:
            return []
        start, end = span
        out = []
        for other in self.list(kinds=("event",), status=("open", "in_progress", "waiting"),
                               due_after=start - 24 * 3600, due_before=end, limit=500):
            other_span = self.span(other)
            if other.id != record.id and other_span is not None and other_span[0] < end and start < other_span[1]:
                out.append(other)
        return out

    def agenda_conflicts(self, *, days: int = 14) -> list[tuple[Record, Record]]:
        """Pares de compromissos sobrepostos de hoje até ``days`` dias (cada par uma única vez)."""
        start, end = self._day_bounds()[0], self._day_bounds(max(0, days - 1))[1]
        events = [r for r in self.list(kinds=("event",), status=("open", "in_progress", "waiting"),
                                       due_after=start, due_before=end, limit=2000) if self.span(r) is not None]
        events.sort(key=lambda r: r.due_at)
        pairs = []
        for i, first in enumerate(events):
            first_end = self.span(first)[1]
            for second in events[i + 1:]:
                if self.span(second)[0] >= first_end:
                    break                                    # ordenados pelo início: nada depois sobrepõe
                pairs.append((first, second))
        return pairs

    # ================================================================ exportação
    def export(self, destination, *, fmt: str = "json", include_deleted: bool = False) -> dict[str, Any]:
        """Exporta registros (e lembretes, no JSON) para um arquivo NOVO — nada é sobrescrito.
        JSON: completo (para guardar ou migrar). CSV: planilha (Excel/LibreOffice), UTF-8 com BOM."""
        import csv
        import json
        from pathlib import Path

        fmt = str(fmt or "json").lower()
        if fmt not in EXPORT_FORMATS:
            raise SecondBrainError(f"formato de exportação desconhecido: {fmt} (use json ou csv)")
        path = Path(destination)
        if path.exists():
            raise SecondBrainError(f"o arquivo já existe: {path.name} — escolha outro nome")
        path.parent.mkdir(parents=True, exist_ok=True)
        where = [] if include_deleted else ["deleted_at IS NULL"]
        records = self.store.select(where, order="created_at", limit=1_000_000)
        partial = path.with_name(path.name + ".partial")
        if fmt == "json":
            reminders = [r.to_dict() for record in records for r in self.store.reminders_for(record.id,
                                                                                               active_only=False)]
            relations = [rel for record in records for rel in self.store.relations(record.id)
                         if rel.get("src") == record.id]
            payload = {"app": "JARVIS", "kind": "second_brain_export", "version": 1, "timezone": self.tz,
                       "exported_at": self.now_wall().isoformat(timespec="seconds"), "count": len(records),
                       "records": [r.to_dict() for r in records], "reminders": reminders, "relations": relations}
            partial.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        else:
            columns = ("id", "kind", "title", "body", "status", "priority", "due_local", "all_day", "end_local",
                       "recurrence", "project_id", "tags", "confirmed", "created_at", "updated_at", "completed_at")
            with partial.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(columns)
                for record in records:
                    row = record.to_dict()
                    row["kind"] = KINDS.get(record.kind, record.kind)
                    row["tags"] = ", ".join(record.tags)
                    for key in ("created_at", "updated_at", "completed_at"):
                        if row.get(key):
                            row[key] = timeutil.format_wall(timeutil.from_epoch(float(row[key]), self.tz))
                    writer.writerow(["" if row.get(c) is None else ("sim" if row[c] else "não")
                                     if isinstance(row.get(c), bool) else row[c] for c in columns])
        partial.replace(path)
        self.db.audit("second_brain", "export", f"{fmt} {len(records)} registro(s)", True)
        return {"path": str(path), "format": fmt, "count": len(records), "bytes": path.stat().st_size}

    def today(self) -> dict[str, Any]:
        start, end = self._day_bounds()
        overdue = self.overdue(limit=50)
        due_today = self.due_between(start, end)
        events = [r for r in due_today if r.kind == "event"]
        tasks = [r for r in due_today if r.kind != "event"]
        urgent = [r for r in self.list(kinds=("task", "study", "deadline"), status=("open", "in_progress"),
                                       order="priority", limit=50) if r.priority >= 3 and r.due_at is None]
        seen, priorities = set(), []
        for record in sorted(overdue + tasks + urgent, key=lambda r: (-r.priority, r.due_at or 9e18)):
            if record.id not in seen:
                seen.add(record.id)
                priorities.append(record)
        upcoming = []
        if self.reminders is not None:
            upcoming = self.reminders.upcoming(limit=6)
        return {"priorities": priorities[:12], "events": events, "overdue": overdue, "tasks_today": tasks,
                "upcoming_reminders": upcoming, "date": self.now_wall().date().isoformat()}

    def timeline(self, *, days: int = 14, offset_days: int = 0) -> list[dict[str, Any]]:
        """Registros com prazo e lembretes próprios, em ordem. Um lembrete no MESMO horário do seu
        registro não aparece duas vezes."""
        start = self._day_bounds(offset_days)[0]
        end = self._day_bounds(offset_days + max(1, days) - 1)[1]          # fim do último dia (respeita horário de verão)
        items = []
        due_of: dict[str, str] = {}
        for record in self.list(kinds=ACTIONABLE, status=("open", "in_progress", "waiting"), due_after=start,
                                due_before=end, limit=500):
            items.append({"at": record.due_at, "kind": "record", "record": record.to_dict()})
            due_of[record.id] = record.due_local
        if self.reminders is not None:
            for rem in self.reminders.upcoming(limit=50):
                if not start <= rem["next_at"] <= end:
                    continue
                if due_of.get(rem["record_id"]) == rem["at_local"]:
                    continue
                items.append({"at": rem["next_at"], "kind": "reminder", "reminder": rem})
        return sorted(items, key=lambda i: i["at"] or 0)

    def projects(self, *, include_done: bool = False) -> list[dict[str, Any]]:
        status = None if include_done else ("open", "in_progress", "waiting")
        out = []
        for project in self.list(kinds=("project",), status=status, order="recent", limit=200):
            rows = self.db.query("SELECT kind, status, COUNT(*) AS n FROM sb_records WHERE project_id=? AND "
                                 "deleted_at IS NULL GROUP BY kind, status", (project.id,))
            counts: dict[str, int] = {}
            open_count = 0
            for row in rows:
                counts[row["kind"]] = counts.get(row["kind"], 0) + row["n"]
                if row["status"] in ("open", "in_progress", "waiting"):
                    open_count += row["n"]
            out.append({"record": project.to_dict(), "counts": counts, "open": open_count})
        return out

    def recent_project(self, *, within: float = 6 * 3600) -> Record | None:
        """O projeto do contexto recente ("esse projeto"): o último projeto tocado, ou o projeto do
        último registro editado. Nada recente → None (a consulta pergunta qual projeto)."""
        since = self.now() - within
        rows = self.store.select(["deleted_at IS NULL", "archived_at IS NULL", "updated_at >= ?",
                                  "(kind = 'project' OR project_id IS NOT NULL)"], [since], limit=1)
        if not rows:
            return None
        record = rows[0]
        return record if record.kind == "project" else self.store.get(record.project_id)

    def ideas_for(self, project_ref: str) -> tuple[Record | None, list[Record]]:
        if CONTEXT_PROJECT_RE.fullmatch(parsing.fold(project_ref or "").strip(" ?.!")):
            project = self.recent_project()
            if project is None:
                raise NeedsClarification("Qual projeto? Diga o nome.")
            project_ref = project.title
        try:
            project = self.resolve(project_ref, kinds=("project",))
        except NeedsClarification:
            raise
        except SecondBrainError:
            project = None
        ideas: dict[str, Record] = {}
        if project is not None:
            for record in self.list(kinds=("idea",), project=project.id):
                ideas[record.id] = record
            for rel in self.related(project.id):
                if rel["record"]["kind"] == "idea":
                    ideas[rel["record"]["id"]] = self.store.get(rel["record"]["id"])
        for record in self.search(project.title if project else project_ref, kinds=("idea",), limit=20):
            ideas.setdefault(record.id, record)
        return project, [r for r in ideas.values() if r is not None]

    def decisions_about(self, topic: str) -> list[Record]:
        """Notas marcadas como decisão (ou que registram "decidi...") sobre o assunto."""
        found = []
        for record in self.search(topic, kinds=("note", "project", "task", "idea"), limit=40):
            text = parsing.fold(f"{record.title} {record.body}")
            if "decisao" in [parsing.fold(t) for t in record.tags] or re.search(r"\bdecid|\bdecisao\b", text):
                found.append(record)
        return found

    def review_queue(self, *, limit: int = 100) -> list[Record]:
        return self.list(confirmed=False, order="recent", limit=limit)

    def history(self, record_id: str) -> list[dict]:
        return self.store.history(record_id)

    def activity(self, *, limit: int = 40) -> list[dict]:
        return self.store.recent_activity(limit=limit)

    # ================================================================ resumo no estado central
    def summary(self) -> dict[str, Any]:
        now = self.now()
        start, end = self._day_bounds()
        open_states = "status IN ('open','in_progress','waiting') AND deleted_at IS NULL AND archived_at IS NULL"
        kinds = "kind IN ('task','event','study','deadline','routine')"
        summary = {
            "open_tasks": self.store.count([open_states, "kind IN ('task','study','deadline')"]),
            "overdue": len(self.overdue(limit=500)),
            "today": self.store.count([open_states, kinds, "due_at >= ? AND due_at < ?"], [start, end]),
            "ideas": self.store.count(["kind='idea'", "deleted_at IS NULL"]),
            "projects": self.store.count([open_states, "kind='project'"]),
            "unreviewed": self.store.count(["confirmed=0", "deleted_at IS NULL"]),
            "trash": self.store.count(["deleted_at IS NOT NULL"]),
            "updated_at": now,
        }
        if self.reminders is not None:
            nxt = self.reminders.upcoming(limit=1)
            summary["next_reminder"] = nxt[0] if nxt else None
            summary["unread_notifications"] = len(self.store.notifications(limit=200, unread_only=True))
        return summary

    def publish_summary(self) -> None:
        if self._state is not None:
            try:
                self._state.update(_source="second_brain", second_brain=self.summary())
            except Exception:
                log.exception("falha ao publicar o resumo do Second Brain")

    # ================================================================ notificações
    def notifications(self, *, limit: int = 100, unread_only: bool = False) -> list[dict]:
        return self.store.notifications(limit=limit, unread_only=unread_only)

    def mark_notifications(self, notification_id: int | None = None, *, state: str = "seen") -> int:
        changed = self.store.set_notification_state(notification_id, state)
        self.publish_summary()
        return changed

    # ================================================================ Neural Graph
    def _link_graph(self, record: Record) -> None:
        """Ideias, projetos, notas, pessoas e estudos também crescem o cérebro do HUB 1."""
        if self._graph is None or record.kind not in GRAPH_TYPES or not record.confirmed:
            return
        try:
            node = self._graph.add_node(GRAPH_TYPES[record.kind], record.title, {"record": record.id},
                                        node_id=f"sb:{record.id}")
            if record.project_id:
                self._graph.connect(f"sb:{record.project_id}", node.id, "RELATED", delta=0.1)
        except (ValueError, KeyError):
            pass


def brief(record: Record) -> dict[str, Any]:
    """Identificação curta de um registro (eventos, avisos de conflito)."""
    return {"id": record.id, "title": record.title, "kind": record.kind, "due_local": record.due_local,
            "end_local": record.end_local}


def describe_record(record: Record, *, now: dt.datetime | None = None) -> str:
    """Linha curta para respostas faladas/escritas."""
    text = record.title
    if record.due_local:
        try:
            text += f" — {timeutil.describe(timeutil.parse_wall(record.due_local), all_day=record.all_day, now=now)}"
        except ValueError:
            pass
    if record.priority >= 3:
        text += f" (prioridade {PRIORITIES[record.priority]})"
    if not record.confirmed:
        text += " [inferido]"
    return text
