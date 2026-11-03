"""Banco PRÓPRIO do gateway (SQLite): agente, dispositivos pareados, pareamentos e auditoria.

Nada de conteúdo de conversa nem memória pessoal: só identificadores, hashes de tokens, nomes de dispositivo,
instantes e o registro de atividades remotas (tipo, dispositivo, IP, detalhe curto).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .security import token_hash

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS agent (
        id INTEGER PRIMARY KEY CHECK (id = 1), token_hash TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
        enrolled REAL NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, created REAL NOT NULL,
        expires REAL NOT NULL, last_seen REAL, revoked REAL, user_agent TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS pairings (
        id TEXT PRIMARY KEY, code TEXT NOT NULL, link_hash TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
        state TEXT NOT NULL DEFAULT 'aberto', claim TEXT NOT NULL DEFAULT '', device_name TEXT NOT NULL DEFAULT '',
        user_agent TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
        device_id TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS idx_pairings_code ON pairings(code)",
    """CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL, device TEXT NOT NULL DEFAULT '',
        ip TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '')""",
    "CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at)",
]


class Store:
    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            for statement in SCHEMA:
                self._db.execute(statement)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _exec(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def _one(self, sql: str, params=()):
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    def _all(self, sql: str, params=()):
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # ------------------------------------------------------------ auditoria
    def audit(self, kind: str, *, device: str = "", ip: str = "", detail: str = "") -> None:
        self._exec("INSERT INTO audit(at, kind, device, ip, detail) VALUES(?,?,?,?,?)",
                   (self._clock(), kind, device, ip, str(detail)[:300]))

    def audit_log(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self._all("SELECT * FROM audit ORDER BY at DESC, id DESC LIMIT ?", (int(limit),))]

    # ------------------------------------------------------------ agente (a matriz-mãe; uma por gateway)
    def set_agent(self, token: str, name: str) -> None:
        """Nova inscrição substitui a anterior (o token antigo deixa de valer)."""
        self._exec("INSERT INTO agent(id, token_hash, name, enrolled) VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "token_hash=excluded.token_hash, name=excluded.name, enrolled=excluded.enrolled",
                   (token_hash(token), name[:80], self._clock()))

    def agent_ok(self, token: str) -> bool:
        row = self._one("SELECT token_hash FROM agent WHERE id=1")
        import hmac
        return bool(row) and hmac.compare_digest(row["token_hash"], token_hash(token))

    # ------------------------------------------------------------ pareamento
    def create_pairing(self, code: str, link: str, ttl: float) -> dict:
        now = self._clock()
        pid = uuid.uuid4().hex[:16]
        self._exec("UPDATE pairings SET state='substituido' WHERE state IN ('aberto','reivindicado')")
        self._exec("INSERT INTO pairings(id, code, link_hash, created, expires) VALUES(?,?,?,?,?)",
                   (pid, code, token_hash(link), now, now + ttl))
        return {"id": pid, "code": code, "expires": now + ttl}

    def find_pairing(self, *, code: str = "", link: str = "") -> sqlite3.Row | None:
        if link:
            return self._one("SELECT * FROM pairings WHERE link_hash=? ORDER BY created DESC LIMIT 1", (token_hash(link),))
        return self._one("SELECT * FROM pairings WHERE code=? ORDER BY created DESC LIMIT 1", (code,))

    def open_pairing(self) -> sqlite3.Row | None:
        return self._one("SELECT * FROM pairings WHERE state='aberto' ORDER BY created DESC LIMIT 1")

    def pairing(self, pid: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM pairings WHERE id=?", (pid,))

    def claim_pairing(self, pid: str, claim: str, device_name: str, user_agent: str, ip: str) -> None:
        self._exec("UPDATE pairings SET state='reivindicado', claim=?, device_name=?, user_agent=?, ip=? WHERE id=?",
                   (claim, device_name[:60], user_agent[:200], ip[:64], pid))

    def wrong_attempt(self, pid: str, max_attempts: int) -> None:
        self._exec("UPDATE pairings SET attempts=attempts+1, state=CASE WHEN attempts+1>=? THEN 'bloqueado' ELSE state "
                   "END WHERE id=?", (max_attempts, pid))

    def finish_pairing(self, pid: str, state: str, *, device_id: str = "") -> None:
        self._exec("UPDATE pairings SET state=?, device_id=? WHERE id=?", (state, device_id, pid))

    # ------------------------------------------------------------ dispositivos
    def add_device(self, name: str, token: str, days: float, user_agent: str, ip: str) -> str:
        did = uuid.uuid4().hex[:12]
        now = self._clock()
        self._exec("INSERT INTO devices(id, name, token_hash, created, expires, user_agent, ip) VALUES(?,?,?,?,?,?,?)",
                   (did, name[:60], token_hash(token), now, now + days * 86400, user_agent[:200], ip[:64]))
        return did

    def device_for(self, token: str) -> sqlite3.Row | None:
        if not token:
            return None
        row = self._one("SELECT * FROM devices WHERE token_hash=?", (token_hash(token),))
        if row is None or row["revoked"] or row["expires"] <= self._clock():
            return None
        return row

    def touch_device(self, did: str) -> None:
        self._exec("UPDATE devices SET last_seen=? WHERE id=?", (self._clock(), did))

    def revoke_device(self, did: str) -> bool:
        return self._exec("UPDATE devices SET revoked=? WHERE id=? AND revoked IS NULL", (self._clock(), did)).rowcount > 0

    def devices(self) -> list[dict]:
        now = self._clock()
        out = []
        for r in self._all("SELECT * FROM devices WHERE revoked IS NULL ORDER BY created DESC"):
            item = {k: r[k] for k in ("id", "name", "created", "expires", "last_seen", "user_agent", "ip")}
            item["expired"] = r["expires"] <= now
            out.append(item)
        return out

    def to_json(self) -> str:
        return json.dumps({"devices": self.devices()}, ensure_ascii=False)
