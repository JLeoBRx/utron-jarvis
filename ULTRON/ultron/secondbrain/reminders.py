"""REMINDERS — lembretes reais, persistentes e sem duplicação.

* uma thread própria dorme até o próximo instante relevante (aviso antecipado, horário, repetição)
  e é acordada quando algo muda — sem varredura constante;
* tudo fica no SQLite: fechar ou reiniciar o JARVIS não perde nada. Ao iniciar, lembretes que
  venceram com o programa fechado são identificados e avisados UMA vez (marcados como
  perdidos); recorrentes saltam para a próxima ocorrência futura sem rajada de avisos antigos;
* cada disparo é registrado em ``sb_fired`` (lembrete, ocorrência, tipo) antes de avisar: a
  deduplicação é atômica e sobrevive a reinícios;
* recorrência diária, dias úteis, semanal e mensal no horário de PAREDE do fuso escolhido
  (o horário de verão não desloca "todo dia às 8h");
* um lembrete ignorado é repetido no máximo ``reminder_max_repeats`` vezes; adiar, concluir ou
  dispensar encerra as repetições. Silêncio (mudo ou horário de silêncio) não descarta nada:
  o aviso vai para a central de notificações sem som, voz ou pop-up.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
import uuid
from typing import Any, Callable

from ..core.events import EventType
from . import timeutil
from .models import Record, Reminder

log = logging.getLogger("ultron.reminders")

GRACE = 120.0                 # s: disparo até 2 min depois do horário ainda é "no horário"
SILENT_IF_LATER = 12 * 3600   # perdido há mais de 12 h: vai só para a central (sem voz nem pop-up)
OVERDUE_HOUR = 9              # aviso diário de atrasados a partir das 9h (horário local)


def in_quiet_hours(spec: str, wall: dt.datetime) -> bool:
    if not spec or "-" not in spec:
        return False
    try:
        start_s, end_s = spec.split("-", 1)
        start = dt.time(*map(int, start_s.split(":")))
        end = dt.time(*map(int, end_s.split(":")))
    except ValueError:
        return False
    now = wall.time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end                 # atravessa a meia-noite (22:00-07:00)


def lead_text(minutes: int) -> str:
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "1 dia" if days == 1 else f"{days} dias"
    if minutes % 60 == 0:
        hours = minutes // 60
        return "1 hora" if hours == 1 else f"{hours} horas"
    return f"{minutes} minutos" if minutes != 1 else "1 minuto"


class ReminderScheduler:
    name = "reminders"

    def __init__(self, service, *, bus=None, state=None, settings_getter: Callable[[], Any] | None = None,
                 clock: Callable[[], float] = time.time, announce: Callable[[dict], None] | None = None):
        self.service = service
        self.store = service.store
        service.reminders = self
        self._bus = bus
        self._state = state
        self._settings = settings_getter or (lambda: None)
        self._clock = clock
        self._announce = announce
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.fired = 0
        self.last_error = ""

    # ================================================================ ciclo de vida
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ultron-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(3.0)
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def health(self) -> dict:
        if not self.enabled:
            return {"status": "WARN", "detail": "lembretes desativados nas configurações"}
        if self._thread is not None and not self._thread.is_alive() and not self._stop.is_set():
            return {"status": "FAIL", "detail": f"agendador parado: {self.last_error or 'motivo desconhecido'}"}
        upcoming = self.upcoming(limit=1)
        detail = f"{len(self.store.scheduled_reminders())} agendado(s)"
        if upcoming:
            detail += f"; próximo {upcoming[0]['when_text']}"
        return {"status": "OK", "detail": detail}

    @property
    def enabled(self) -> bool:
        return bool(getattr(self._settings(), "reminders", True))

    @property
    def tz(self) -> str:
        return str(getattr(self._settings(), "timezone", "") or "")

    def wake(self) -> None:
        self._wake.set()

    # ================================================================ agendamento
    def schedule(self, record: Record, *, leads: list | None = None, at: dt.datetime | None = None,
                 recurrence: str | None = None, pinned: bool = False) -> Reminder:
        wall = at or (timeutil.parse_wall(record.due_local) if record.due_local else None)
        if wall is None:
            raise ValueError("lembrete sem data/hora")
        if record.all_day and at is None:
            wall = wall.replace(hour=9, minute=0)            # prazo de dia inteiro: lembra às 9h do dia
        tz = record.tz or self.tz
        now = self._clock()
        leads = sorted({int(x) for x in (leads or []) if 0 < int(x) <= 43200}, reverse=True)
        rem = Reminder(f"m_{uuid.uuid4().hex[:12]}", record.id, timeutil.format_wall(wall), tz,
                       timeutil.to_epoch(wall, tz), leads, record.recurrence if recurrence is None else recurrence,
                       wall.day, "scheduled", None, 0, now, now, None, bool(pinned))
        with self._lock:
            self.store.insert_reminder(rem)
            self.store.log(record.id, "reminder_set", {"at": rem.at_local, "leads": leads,
                                                       "recurrence": rem.recurrence}, "system")
        self._wake.set()
        return rem

    def reschedule_record(self, record: Record) -> None:
        """O horário do registro mudou (edição, conclusão de ocorrência, restauração)."""
        with self._lock:
            reminders = self.store.reminders_for(record.id, active_only=False)
            for rem in reminders:
                if rem.status == "cancelled" and record.deleted_at:
                    continue
                if rem.pinned:                               # horário próprio: só cancela se o registro sair
                    if record.status in ("done", "cancelled") or record.deleted_at or record.archived_at:
                        rem.status = "cancelled"
                    elif rem.status == "cancelled" and rem.next_at > self._clock():
                        rem.status = "scheduled"
                    rem.updated_at = self._clock()
                    self.store.save_reminder(rem)
                    continue
                if not record.due_local or record.status in ("done", "cancelled") or record.deleted_at \
                        or record.archived_at:
                    rem.status = "cancelled"
                else:
                    wall = timeutil.parse_wall(record.due_local)
                    if record.all_day:
                        wall = wall.replace(hour=9, minute=0)
                    rem.at_local, rem.tz = timeutil.format_wall(wall), record.tz or self.tz
                    rem.next_at = timeutil.to_epoch(wall, rem.tz)
                    rem.recurrence, rem.anchor_day = record.recurrence, wall.day
                    rem.status, rem.repeats, rem.snoozed_until = "scheduled", 0, None
                rem.updated_at = self._clock()
                self.store.save_reminder(rem)
        self._wake.set()

    def finish_record(self, record: Record, *, cancelled: bool = False) -> None:
        with self._lock:
            for rem in self.store.reminders_for(record.id):
                rem.status = "cancelled" if cancelled else "done"
                rem.updated_at = self._clock()
                self.store.save_reminder(rem)
        self._wake.set()

    def snooze(self, reminder_id: str, minutes: float) -> Reminder:
        minutes = max(1.0, min(24 * 60.0, float(minutes)))
        with self._lock:
            rem = self.store.reminder(reminder_id)
            if rem is None:
                raise ValueError("lembrete não encontrado")
            until = self._clock() + minutes * 60
            rem.next_at, rem.snoozed_until, rem.repeats = until, until, 0
            rem.at_local = timeutil.format_wall(timeutil.from_epoch(until, rem.tz))
            rem.leads = []                                   # adiado: avisa só no novo horário
            rem.status, rem.updated_at = "scheduled", self._clock()
            self.store.save_reminder(rem)
            self.store.log(rem.record_id, "snoozed", {"minutes": minutes, "until": rem.at_local}, "user")
        self._emit(EventType.REMINDER_SNOOZED, id=rem.id, record_id=rem.record_id, minutes=minutes,
                   until=rem.next_at, when_text=self._when_text(rem.next_at, rem.tz))
        self._wake.set()
        self.service.publish_summary()
        return rem

    def dismiss(self, reminder_id: str) -> Reminder | None:
        """Ciente: encerra as repetições desta ocorrência (recorrentes seguem para a próxima)."""
        with self._lock:
            rem = self.store.reminder(reminder_id)
            if rem is None:
                return None
            if rem.recurrence:
                self._advance(rem, after=self._clock())
            else:
                rem.status = "done"
            rem.updated_at = self._clock()
            self.store.save_reminder(rem)
        self._wake.set()
        self.service.publish_summary()
        return rem

    def latest_fired(self, *, within: float = 3 * 3600) -> Reminder | None:
        """O lembrete avisado mais recentemente (alvo de "adie o lembrete")."""
        rows = self.store.db.query("SELECT * FROM sb_reminders WHERE last_fired_at IS NOT NULL AND last_fired_at >= ? "
                                   "ORDER BY last_fired_at DESC LIMIT 1", (self._clock() - within,))
        return Reminder.from_row(rows[0]) if rows else None

    def upcoming(self, *, limit: int = 10) -> list[dict]:
        out = []
        for rem in self.store.upcoming_reminders(after=self._clock() - GRACE, limit=limit * 2):
            record = self.store.get(rem.record_id)
            if record is None or record.deleted_at:
                continue
            out.append({**rem.to_dict(), "title": record.title, "kind": record.kind,
                        "when_text": self._when_text(rem.next_at, rem.tz)})
            if len(out) >= limit:
                break
        return out

    def _when_text(self, epoch: float, tz: str) -> str:
        return timeutil.describe(timeutil.from_epoch(epoch, tz), now=timeutil.from_epoch(self._clock(), tz))

    # ================================================================ motor
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                wait = self.process()
                self.last_error = ""
            except Exception as exc:                         # o agendador nunca morre por um registro ruim
                self.last_error = f"{type(exc).__name__}: {exc}"[:200]
                log.exception("falha no agendador de lembretes")
                wait = 5.0
            self._wake.wait(max(0.2, min(30.0, wait)))
            self._wake.clear()

    def process(self) -> float:
        """Dispara o que venceu e devolve quantos segundos dormir até o próximo evento."""
        now = self._clock()
        if not self.enabled:
            return 30.0
        settings = self._settings()
        repeat_after = float(getattr(settings, "reminder_repeat_minutes", 10.0)) * 60
        max_repeats = int(getattr(settings, "reminder_max_repeats", 2))
        next_event = now + 30.0
        with self._lock:
            for rem in self.store.scheduled_reminders():
                record = self.store.get(rem.record_id)
                if record is None or record.deleted_at or record.archived_at or record.status in ("done", "cancelled"):
                    rem.status = "cancelled" if record is None or record.deleted_at else "done"
                    self.store.save_reminder(rem)
                    continue
                if rem.recurrence and rem.next_at < now - GRACE and not self.store.was_fired(
                        rem.id, self._occurrence(rem), "due"):
                    self._catch_up(rem)                      # várias ocorrências perdidas: só a última conta
                occurrence = self._occurrence(rem)
                if rem.next_at > now:                         # futuro: avisos antecipados
                    for lead in rem.leads:
                        at = rem.next_at - lead * 60
                        if at <= now:
                            if self.store.mark_fired(rem.id, occurrence, f"lead:{lead}"):
                                self._fire(rem, record, lead=lead, now=now)
                        else:
                            next_event = min(next_event, at)
                    next_event = min(next_event, rem.next_at)
                    continue
                if self.store.mark_fired(rem.id, occurrence, "due"):
                    late = now - rem.next_at
                    self._fire(rem, record, late=late if late > GRACE else 0.0, now=now)
                    rem.last_fired_at, rem.repeats = now, 0
                    if rem.recurrence:
                        self._advance(rem, after=now)
                        self._sync_record(record, rem)
                        next_event = min(next_event, rem.next_at)
                    elif max_repeats <= 0 or late > GRACE:      # perdido: aviso único, sem repetições
                        rem.status = "done"
                    else:
                        next_event = min(next_event, now + repeat_after)
                    rem.updated_at = now
                    self.store.save_reminder(rem)
                    continue
                if rem.recurrence:                            # já avisado (ex.: queda antes de avançar)
                    self._advance(rem, after=now)
                    rem.updated_at = now
                    self.store.save_reminder(rem)
                    self._sync_record(record, rem)
                    next_event = min(next_event, rem.next_at)
                    continue
                # já avisado e ainda sem resposta: repete no máximo ``max_repeats`` vezes
                if rem.repeats < max_repeats:
                    at = (rem.last_fired_at or rem.next_at) + repeat_after
                    if now >= at:
                        if self.store.mark_fired(rem.id, occurrence, f"repeat:{rem.repeats + 1}"):
                            self._fire(rem, record, repeat=rem.repeats + 1, now=now)
                        rem.repeats += 1
                        rem.last_fired_at, rem.updated_at = now, now
                        if rem.repeats >= max_repeats:
                            rem.status = "done"
                        self.store.save_reminder(rem)
                        if rem.status == "scheduled":
                            next_event = min(next_event, now + repeat_after)
                    else:
                        next_event = min(next_event, at)
                else:
                    rem.status, rem.updated_at = "done", now
                    self.store.save_reminder(rem)
            self._overdue_digest(now)
        return max(0.0, next_event - self._clock())

    @staticmethod
    def _occurrence(rem: Reminder) -> str:
        return f"{rem.next_at:.0f}"

    def _advance(self, rem: Reminder, *, after: float) -> None:
        wall = timeutil.parse_wall(rem.at_local)
        nxt = timeutil.next_occurrence(wall, rem.recurrence, after=timeutil.from_epoch(after, rem.tz),
                                       anchor_day=rem.anchor_day)
        if nxt is None:
            rem.status = "done"
            return
        rem.at_local, rem.next_at = timeutil.format_wall(nxt), timeutil.to_epoch(nxt, rem.tz)
        rem.repeats, rem.snoozed_until = 0, None

    def _catch_up(self, rem: Reminder) -> None:
        """Recorrente com ocorrências perdidas: posiciona na ÚLTIMA ocorrência vencida (que será
        avisada uma vez como perdida); as anteriores ficam registradas como não avisadas."""
        now_wall = timeutil.from_epoch(self._clock(), rem.tz)
        wall = timeutil.parse_wall(rem.at_local)
        last = wall
        for _ in range(4000):
            nxt = timeutil.next_occurrence(last, rem.recurrence, after=last, anchor_day=rem.anchor_day)
            if nxt is None or nxt > now_wall:
                break
            last = nxt
        if last != wall:
            rem.at_local, rem.next_at = timeutil.format_wall(last), timeutil.to_epoch(last, rem.tz)
            self.store.save_reminder(rem)

    def _sync_record(self, record: Record, rem: Reminder) -> None:
        """Rotina recorrente: o próximo horário também vale para o registro."""
        if rem.pinned:
            return
        if record.recurrence and record.due_local != rem.at_local:
            record.due_local, record.due_at, record.updated_at = rem.at_local, rem.next_at, self._clock()
            self.store.save(record)
            self._emit(EventType.RECORD_UPDATED, record=record.to_dict(), change="occurrence")

    def _silent(self, now: float) -> bool:
        settings = self._settings()
        if bool(getattr(settings, "notifications_muted", False)):
            return True
        return in_quiet_hours(str(getattr(settings, "quiet_hours", "") or ""), timeutil.from_epoch(now, self.tz))

    def _fire(self, rem: Reminder, record: Record, *, lead: int | None = None, late: float = 0.0,
              repeat: int = 0, now: float) -> None:
        when_text = self._when_text(rem.next_at, rem.tz)
        silent = self._silent(now) or late > SILENT_IF_LATER
        if lead:
            title = f"Em {lead_text(lead)}: {record.title}"
            kind = "lead"
        elif late:
            title = f"Lembrete perdido: {record.title}"
            kind = "missed"
        else:
            title = f"Lembrete: {record.title}" + (" (repetição)" if repeat else "")
            kind = "reminder"
        body = when_text + (" · enquanto o JARVIS estava fechado" if late else "")
        notification_id = self.store.add_notification(kind, title, body, record_id=record.id, reminder_id=rem.id,
                                                      silent=silent)
        self.store.log(record.id, "reminded", {"kind": kind, "occurrence": rem.at_local, "silent": silent}, "system")
        self.fired += 1
        payload = {"id": rem.id, "record_id": record.id, "title": record.title, "record_kind": record.kind,
                   "notice": title, "when": rem.next_at, "when_text": when_text,
                   "lead": lead_text(lead) if lead else None, "lead_minutes": lead, "late": bool(late),
                   "repeat": repeat, "silent": silent, "notification_id": notification_id, "kind": kind}
        self._emit(EventType.REMINDER_DUE, **payload)
        if self._announce is not None and not silent:
            try:
                self._announce(payload)
            except Exception:
                log.exception("falha ao anunciar lembrete")
        self.service.publish_summary()

    def _overdue_digest(self, now: float) -> None:
        if not bool(getattr(self._settings(), "overdue_alerts", True)):
            return
        wall = timeutil.from_epoch(now, self.tz)
        if wall.hour < OVERDUE_HOUR:
            return
        overdue = self.service.overdue(limit=20)
        if not overdue or not self.store.mark_fired("overdue", wall.date().isoformat(), "daily"):
            return
        titles = ", ".join(r.title for r in overdue[:4]) + ("…" if len(overdue) > 4 else "")
        silent = self._silent(now)
        title = f"{len(overdue)} tarefa(s) atrasada(s)"
        notification_id = self.store.add_notification("overdue", title, titles, silent=silent)
        self._emit(EventType.NOTIFICATION, kind="overdue", title=title, body=titles, silent=silent,
                   popup=not silent, notification_id=notification_id, count=len(overdue))

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="reminders")
