"""Armazenamento do Second Brain no banco único do JARVIS (SQLite, migrações versionadas).

Busca de texto: índice FTS5 sem acentos (``unicode61 remove_diacritics``) mantido por gatilhos.
Se o SQLite da máquina não tiver FTS5, a busca usa a coluna ``search_text`` normalizada
(mesmo resultado, menos ranqueamento) — nunca depende de serviço externo.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Iterable

from ..memory.store import Database
from .models import Record, Reminder
from .parsing import fold

log = logging.getLogger("ultron.secondbrain.store")

RECORD_COLUMNS = ("id", "kind", "title", "body", "status", "priority", "due_local", "due_at", "all_day", "end_local",
                  "tz", "recurrence", "project_id", "tags", "origin", "origin_detail", "confirmed", "confidence",
                  "data", "search_text", "created_at", "updated_at", "completed_at", "archived_at", "deleted_at")
REMINDER_COLUMNS = ("id", "record_id", "at_local", "tz", "next_at", "leads", "recurrence", "anchor_day", "status",
                    "snoozed_until", "repeats", "created_at", "updated_at", "last_fired_at", "pinned")

FTS_SQL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS sb_fts USING fts5(title, body, tags, content='sb_records', "
    "content_rowid='seq', tokenize='unicode61 remove_diacritics 2')",
    "CREATE TRIGGER IF NOT EXISTS sb_fts_ai AFTER INSERT ON sb_records BEGIN "
    "INSERT INTO sb_fts(rowid, title, body, tags) VALUES (new.seq, new.title, new.body, new.tags); END",
    "CREATE TRIGGER IF NOT EXISTS sb_fts_ad AFTER DELETE ON sb_records BEGIN "
    "INSERT INTO sb_fts(sb_fts, rowid, title, body, tags) VALUES ('delete', old.seq, old.title, old.body, old.tags); END",
    "CREATE TRIGGER IF NOT EXISTS sb_fts_au AFTER UPDATE OF title, body, tags ON sb_records BEGIN "
    "INSERT INTO sb_fts(sb_fts, rowid, title, body, tags) VALUES ('delete', old.seq, old.title, old.body, old.tags); "
    "INSERT INTO sb_fts(rowid, title, body, tags) VALUES (new.seq, new.title, new.body, new.tags); END",
)


def search_text(title: str, body: str, tags: Iterable[str]) -> str:
    return fold(" ".join([title, body, " ".join(tags)]))


def fts_query(text: str) -> str:
    """Termos com prefixo, todos obrigatórios; aspas e operadores do usuário são neutralizados."""
    words = [w for w in "".join(c if c.isalnum() else " " for c in fold(text)).split() if len(w) >= 2]
    return " ".join(f'"{w}"*' for w in words[:12])


class SecondBrainStore:
    def __init__(self, db: Database):
        self.db = db
        self.fts = False

    def ensure_fts(self) -> bool:
        try:
            exists = self.db.one("SELECT name FROM sqlite_master WHERE name='sb_fts'") is not None
            with self.db.transaction() as conn:
                for sql in FTS_SQL:
                    conn.execute(sql)
                if not exists:
                    conn.execute("INSERT INTO sb_fts(sb_fts) VALUES ('rebuild')")   # índice de registros existentes
            self.fts = True
        except sqlite3.Error as exc:
            log.info("FTS5 indisponível (%s); busca por texto normalizado", exc)
            self.fts = False
        return self.fts

    # ------------------------------------------------------------ registros
    def insert(self, rec: Record) -> None:
        values = self._record_values(rec)
        self.db.execute(f"INSERT INTO sb_records({', '.join(RECORD_COLUMNS)}) "
                        f"VALUES({', '.join('?' for _ in RECORD_COLUMNS)})", values)

    def save(self, rec: Record) -> None:
        values = self._record_values(rec)
        sets = ", ".join(f"{c}=?" for c in RECORD_COLUMNS[1:])
        self.db.execute(f"UPDATE sb_records SET {sets} WHERE id=?", values[1:] + [rec.id])

    @staticmethod
    def _record_values(rec: Record) -> list:
        return [rec.id, rec.kind, rec.title, rec.body, rec.status, int(rec.priority), rec.due_local, rec.due_at,
                int(rec.all_day), rec.end_local, rec.tz, rec.recurrence, rec.project_id,
                json.dumps(list(rec.tags), ensure_ascii=False), rec.origin, rec.origin_detail, int(rec.confirmed),
                float(rec.confidence), json.dumps(rec.data, ensure_ascii=False, default=str),
                search_text(rec.title, rec.body, rec.tags), rec.created_at, rec.updated_at, rec.completed_at,
                rec.archived_at, rec.deleted_at]

    def get(self, record_id: str) -> Record | None:
        row = self.db.one("SELECT * FROM sb_records WHERE id=?", (record_id,))
        return Record.from_row(row) if row else None

    def purge(self, record_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM sb_records WHERE id=?", (record_id,))
            conn.execute("DELETE FROM sb_relations WHERE src=? OR dst=?", (record_id, record_id))
            conn.execute("DELETE FROM sb_history WHERE record_id=?", (record_id,))
            ids = [r[0] for r in conn.execute("SELECT id FROM sb_reminders WHERE record_id=?", (record_id,))]
            conn.execute("DELETE FROM sb_reminders WHERE record_id=?", (record_id,))
            for rid in ids:
                conn.execute("DELETE FROM sb_fired WHERE reminder_id=?", (rid,))
            conn.execute("UPDATE sb_records SET project_id=NULL WHERE project_id=?", (record_id,))
            conn.execute("DELETE FROM sb_notifications WHERE record_id=?", (record_id,))

    def select(self, where: list[str] | None = None, params: list | None = None, *, order: str = "updated_at DESC",
               limit: int = 200) -> list[Record]:
        sql = "SELECT * FROM sb_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order} LIMIT ?"
        return [Record.from_row(r) for r in self.db.query(sql, list(params or []) + [int(limit)])]

    def count(self, where: list[str] | None = None, params: list | None = None) -> int:
        sql = "SELECT COUNT(*) FROM sb_records" + (" WHERE " + " AND ".join(where) if where else "")
        row = self.db.one(sql, list(params or []))
        return int(row[0]) if row else 0

    def search_ids(self, text: str, *, limit: int = 100) -> list[str]:
        """Ids dos registros que contêm todos os termos (ranqueados quando há FTS5)."""
        if self.fts:
            query = fts_query(text)
            if not query:
                return []
            try:
                rows = self.db.query("SELECT r.id FROM sb_fts f JOIN sb_records r ON r.seq = f.rowid "
                                     "WHERE sb_fts MATCH ? ORDER BY bm25(sb_fts) LIMIT ?", (query, int(limit)))
                return [r[0] for r in rows]
            except sqlite3.Error as exc:
                log.debug("consulta FTS falhou (%s); usando texto normalizado", exc)
        words = [w for w in "".join(c if c.isalnum() else " " for c in fold(text)).split() if len(w) >= 2][:8]
        if not words:
            return []
        where = " AND ".join("search_text LIKE ?" for _ in words)
        rows = self.db.query(f"SELECT id FROM sb_records WHERE {where} ORDER BY updated_at DESC LIMIT ?",
                             [f"%{w}%" for w in words] + [int(limit)])
        return [r[0] for r in rows]

    # ------------------------------------------------------------ relações e histórico
    def relate(self, src: str, dst: str, type_: str) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO sb_relations(src, dst, type, created_at) VALUES(?,?,?,?)",
                              (src, dst, type_, time.time()))
        return cur.rowcount > 0

    def unrelate(self, src: str, dst: str, type_: str) -> bool:
        return self.db.execute("DELETE FROM sb_relations WHERE src=? AND dst=? AND type=?",
                               (src, dst, type_)).rowcount > 0

    def relations(self, record_id: str) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT src, dst, type FROM sb_relations WHERE src=? OR dst=?", (record_id, record_id))
        return [dict(r) for r in rows]

    def related_ids(self, record_id: str, type_: str, *, incoming: bool) -> list[str]:
        column, other = ("dst", "src") if incoming else ("src", "dst")
        rows = self.db.query(f"SELECT {other} FROM sb_relations WHERE {column}=? AND type=?", (record_id, type_))
        return [r[0] for r in rows]

    def log(self, record_id: str, action: str, changes: dict | None = None, origin: str = "") -> None:
        self.db.execute("INSERT INTO sb_history(record_id, at, action, changes, origin) VALUES(?,?,?,?,?)",
                        (record_id, time.time(), action, json.dumps(changes or {}, ensure_ascii=False, default=str),
                         origin))

    def history(self, record_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT at, action, changes, origin FROM sb_history WHERE record_id=? "
                             "ORDER BY id DESC LIMIT ?", (record_id, int(limit)))
        out = []
        for r in rows:
            try:
                changes = json.loads(r["changes"])
            except ValueError:
                changes = {}
            out.append({"at": r["at"], "action": r["action"], "changes": changes, "origin": r["origin"]})
        return out

    def recent_activity(self, *, limit: int = 40) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT h.record_id, h.at, h.action, h.origin, r.title, r.kind FROM sb_history h "
                             "LEFT JOIN sb_records r ON r.id = h.record_id ORDER BY h.id DESC LIMIT ?", (int(limit),))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ lembretes
    def insert_reminder(self, rem: Reminder) -> None:
        values = self._reminder_values(rem)
        self.db.execute(f"INSERT INTO sb_reminders({', '.join(REMINDER_COLUMNS)}) "
                        f"VALUES({', '.join('?' for _ in REMINDER_COLUMNS)})", values)

    def save_reminder(self, rem: Reminder) -> None:
        values = self._reminder_values(rem)
        sets = ", ".join(f"{c}=?" for c in REMINDER_COLUMNS[1:])
        self.db.execute(f"UPDATE sb_reminders SET {sets} WHERE id=?", values[1:] + [rem.id])

    @staticmethod
    def _reminder_values(rem: Reminder) -> list:
        return [rem.id, rem.record_id, rem.at_local, rem.tz, float(rem.next_at), json.dumps(list(rem.leads)),
                rem.recurrence, rem.anchor_day, rem.status, rem.snoozed_until, int(rem.repeats), rem.created_at,
                rem.updated_at, rem.last_fired_at, int(bool(rem.pinned))]

    def reminder(self, reminder_id: str) -> Reminder | None:
        row = self.db.one("SELECT * FROM sb_reminders WHERE id=?", (reminder_id,))
        return Reminder.from_row(row) if row else None

    def reminders_for(self, record_id: str, *, active_only: bool = True) -> list[Reminder]:
        sql = "SELECT * FROM sb_reminders WHERE record_id=?" + (" AND status='scheduled'" if active_only else "")
        return [Reminder.from_row(r) for r in self.db.query(sql + " ORDER BY next_at", (record_id,))]

    def scheduled_reminders(self) -> list[Reminder]:
        return [Reminder.from_row(r) for r in
                self.db.query("SELECT * FROM sb_reminders WHERE status='scheduled' ORDER BY next_at")]

    def upcoming_reminders(self, *, after: float, limit: int = 20) -> list[Reminder]:
        rows = self.db.query("SELECT * FROM sb_reminders WHERE status='scheduled' AND next_at >= ? ORDER BY next_at "
                             "LIMIT ?", (after, int(limit)))
        return [Reminder.from_row(r) for r in rows]

    def mark_fired(self, reminder_id: str, occurrence: str, kind: str) -> bool:
        """Registra um disparo; devolve False se ele já tinha acontecido (deduplicação atômica)."""
        cur = self.db.execute("INSERT OR IGNORE INTO sb_fired(reminder_id, occurrence, kind, fired_at) "
                              "VALUES(?,?,?,?)", (reminder_id, occurrence, kind, time.time()))
        return cur.rowcount > 0

    def was_fired(self, reminder_id: str, occurrence: str, kind: str) -> bool:
        return self.db.one("SELECT 1 FROM sb_fired WHERE reminder_id=? AND occurrence=? AND kind=?",
                           (reminder_id, occurrence, kind)) is not None

    def prune_fired(self, *, older_than: float) -> None:
        self.db.execute("DELETE FROM sb_fired WHERE fired_at < ?", (older_than,))

    # ------------------------------------------------------------ central de notificações
    def add_notification(self, kind: str, title: str, body: str = "", *, record_id: str | None = None,
                         reminder_id: str | None = None, silent: bool = False) -> int:
        cur = self.db.execute("INSERT INTO sb_notifications(at, kind, title, body, record_id, reminder_id, state, silent)"
                              " VALUES(?,?,?,?,?,?,?,?)", (time.time(), kind, title[:200], body[:400], record_id,
                                                          reminder_id, "new", int(silent)))
        self.db.execute("DELETE FROM sb_notifications WHERE id NOT IN "
                        "(SELECT id FROM sb_notifications ORDER BY id DESC LIMIT 500)")
        return int(cur.lastrowid)

    def notifications(self, *, limit: int = 100, unread_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM sb_notifications" + (" WHERE state='new'" if unread_only else "")
        return [dict(r) for r in self.db.query(sql + " ORDER BY id DESC LIMIT ?", (int(limit),))]

    def set_notification_state(self, notification_id: int | None, state: str) -> int:
        if notification_id is None:
            return self.db.execute("UPDATE sb_notifications SET state=? WHERE state='new'", (state,)).rowcount
        return self.db.execute("UPDATE sb_notifications SET state=? WHERE id=?", (state, notification_id)).rowcount
