"""Armazenamento persistente do JARVIS (SQLite, modo WAL).

Uma única base para todas as memórias, objetivos, grafo e inventário. As migrações são
versionadas e idempotentes. Textos que parecem segredos (senhas, tokens, cartões) são
recusados antes de qualquer gravação.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger("ultron.store")

SECRET_RE = re.compile(
    r"(senha|password|passwd|token|api[_ -]?key|secret|credencia|private key|chave privada|"
    r"seed phrase|cvv|\bpin\b|c[oó]digo de (?:seguran[cç]a|verifica[cç][aã]o|acesso)|\b2fa\b|\botp\b|"
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b(?:\d[ -]?){13,19}\b)",
    re.IGNORECASE,
)


def looks_secret(text: Any) -> bool:
    return bool(SECRET_RE.search(str(text or "")))


def clean_text(value: Any, limit: int, *, field: str = "texto", allow_empty: bool = False) -> str:
    text = " ".join(str(value or "").split())
    if not text and not allow_empty:
        raise ValueError(f"{field} vazio")
    if len(text) > limit:
        raise ValueError(f"{field} excede {limit} caracteres")
    if looks_secret(text):
        raise ValueError("o JARVIS não armazena senhas, tokens ou dados financeiros")
    return text


MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [
        """CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL UNIQUE,
            fact TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'user',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            access_count INTEGER NOT NULL DEFAULT 0,
            last_access REAL)""",
        """CREATE TABLE IF NOT EXISTS preferences (
            name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            goal_id TEXT,
            summary TEXT NOT NULL,
            actions TEXT NOT NULL DEFAULT '[]',
            outcome TEXT NOT NULL DEFAULT '',
            success INTEGER,
            evidence TEXT NOT NULL DEFAULT '[]',
            context TEXT NOT NULL DEFAULT '{}',
            started_at REAL NOT NULL,
            finished_at REAL,
            importance REAL NOT NULL DEFAULT 0.5)""",
        """CREATE TABLE IF NOT EXISTS procedures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            trigger TEXT NOT NULL,
            steps TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'learned',
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            last_used REAL)""",
        """CREATE TABLE IF NOT EXISTS automations (
            name TEXT PRIMARY KEY,
            trigger_text TEXT NOT NULL UNIQUE,
            tool_name TEXT NOT NULL,
            arguments TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1)""",
        """CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL,
            verified INTEGER, created_at REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS session_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT NOT NULL, created_at REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS goals (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.0,
            risk TEXT NOT NULL DEFAULT 'low',
            source TEXT NOT NULL DEFAULT 'user',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            tasks TEXT NOT NULL DEFAULT '[]',
            dependencies TEXT NOT NULL DEFAULT '[]',
            evidence TEXT NOT NULL DEFAULT '[]',
            result TEXT NOT NULL DEFAULT '',
            history TEXT NOT NULL DEFAULT '[]')""",
        """CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            label TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '{}',
            strength REAL NOT NULL DEFAULT 0.3,
            use_count INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            last_used REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS graph_edges (
            src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 0.2,
            use_count INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL, last_used REAL NOT NULL,
            PRIMARY KEY (src, dst, type))""",
        "CREATE INDEX IF NOT EXISTS idx_edges_dst ON graph_edges(dst)",
        "CREATE INDEX IF NOT EXISTS idx_nodes_type ON graph_nodes(type)",
        """CREATE TABLE IF NOT EXISTS network_devices (
            key TEXT PRIMARY KEY,
            ip TEXT NOT NULL, mac TEXT NOT NULL DEFAULT '', hostname TEXT NOT NULL DEFAULT '',
            vendor TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL DEFAULT 'unknown',
            first_seen REAL NOT NULL, last_seen REAL NOT NULL, latency_ms REAL)""",
        """CREATE TABLE IF NOT EXISTS creations (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_id TEXT,
            data TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS idx_creations_parent ON creations(parent_id)",
        """CREATE TABLE IF NOT EXISTS images (
            id TEXT PRIMARY KEY,
            concept_id TEXT,
            path TEXT NOT NULL,
            prompt TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)""",
    ]),
    # v2 — SECOND BRAIN: registros pessoais pesquisáveis, relações, histórico, lembretes e notificações
    (2, [
        """CREATE TABLE IF NOT EXISTS sb_records (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            priority INTEGER NOT NULL DEFAULT 2,
            due_local TEXT NOT NULL DEFAULT '',
            due_at REAL,
            all_day INTEGER NOT NULL DEFAULT 0,
            end_local TEXT NOT NULL DEFAULT '',
            tz TEXT NOT NULL DEFAULT '',
            recurrence TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            origin TEXT NOT NULL DEFAULT 'user',
            origin_detail TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL DEFAULT 1.0,
            data TEXT NOT NULL DEFAULT '{}',
            search_text TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            completed_at REAL,
            archived_at REAL,
            deleted_at REAL)""",
        "CREATE INDEX IF NOT EXISTS idx_sb_kind_status ON sb_records(kind, status)",
        "CREATE INDEX IF NOT EXISTS idx_sb_due ON sb_records(due_at)",
        "CREATE INDEX IF NOT EXISTS idx_sb_project ON sb_records(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_sb_deleted ON sb_records(deleted_at)",
        "CREATE INDEX IF NOT EXISTS idx_sb_updated ON sb_records(updated_at)",
        """CREATE TABLE IF NOT EXISTS sb_relations (
            src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL, created_at REAL NOT NULL,
            PRIMARY KEY (src, dst, type))""",
        "CREATE INDEX IF NOT EXISTS idx_sb_rel_dst ON sb_relations(dst)",
        """CREATE TABLE IF NOT EXISTS sb_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id TEXT NOT NULL, at REAL NOT NULL, action TEXT NOT NULL,
            changes TEXT NOT NULL DEFAULT '{}', origin TEXT NOT NULL DEFAULT '')""",
        "CREATE INDEX IF NOT EXISTS idx_sb_hist_record ON sb_history(record_id)",
        """CREATE TABLE IF NOT EXISTS sb_reminders (
            id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            at_local TEXT NOT NULL,
            tz TEXT NOT NULL DEFAULT '',
            next_at REAL NOT NULL,
            leads TEXT NOT NULL DEFAULT '[]',
            recurrence TEXT NOT NULL DEFAULT '',
            anchor_day INTEGER,
            status TEXT NOT NULL DEFAULT 'scheduled',
            snoozed_until REAL,
            repeats INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_fired_at REAL,
            pinned INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_sb_rem_next ON sb_reminders(status, next_at)",
        "CREATE INDEX IF NOT EXISTS idx_sb_rem_record ON sb_reminders(record_id)",
        """CREATE TABLE IF NOT EXISTS sb_fired (
            reminder_id TEXT NOT NULL, occurrence TEXT NOT NULL, kind TEXT NOT NULL, fired_at REAL NOT NULL,
            PRIMARY KEY (reminder_id, occurrence, kind))""",
        """CREATE TABLE IF NOT EXISTS sb_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at REAL NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
            record_id TEXT, reminder_id TEXT, state TEXT NOT NULL DEFAULT 'new', silent INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS idx_sb_notif_at ON sb_notifications(at)",
    ]),
    # v3 — NETWORK INTELLIGENCE: inventário com confiança, métodos, IPv6, notas e dispositivos confiáveis.
    # "offline" passa a ser "absent": não ser visto numa varredura não prova que o aparelho saiu da rede.
    (3, [
        "ALTER TABLE network_devices ADD COLUMN alias TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE network_devices ADD COLUMN notes TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE network_devices ADD COLUMN trusted INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE network_devices ADD COLUMN ipv6 TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE network_devices ADD COLUMN interface TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE network_devices ADD COLUMN segment TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE network_devices ADD COLUMN methods TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE network_devices ADD COLUMN confidence REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE network_devices ADD COLUMN missed_scans INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE network_devices ADD COLUMN vendor_source TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE network_devices ADD COLUMN extra TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE network_devices ADD COLUMN last_check TEXT NOT NULL DEFAULT '{}'",
        "UPDATE network_devices SET status='absent' WHERE status='offline'",
        "CREATE INDEX IF NOT EXISTS idx_net_status ON network_devices(status)",
    ]),
    # v4 — HISTÓRICO DE ATIVIDADES (JARVIS ULTIMATE): o ciclo de vida estruturado de cada pedido, ação,
    # confirmação, consulta à TARDIS e comando ao Noctário. A tabela ``audit`` continua como trilha de
    # auditoria de baixo nível (só acrescenta texto); aqui o MESMO registro muda de estado
    # (recebido → executando → concluído/falhou), com origem, entrada, resultado, erro e duração.
    (4, [
        """CREATE TABLE IF NOT EXISTS activity (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL, origin TEXT NOT NULL, title TEXT NOT NULL,
            input TEXT NOT NULL DEFAULT '', state TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
            parent TEXT NOT NULL DEFAULT '', ref TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '{}',
            started_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL)""",
        "CREATE INDEX IF NOT EXISTS idx_activity_started ON activity(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_activity_ref ON activity(ref)",
    ]),
    # v5 — TARDIS: as tarefas do protocolo (entrada, estado, resultado, erro, tempos, registro, modelo) e a
    # memória de projeto (decisões, notas e histórico de parâmetros).
    (5, [
        """CREATE TABLE IF NOT EXISTS tardis_tasks (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL, origin TEXT NOT NULL, input TEXT NOT NULL DEFAULT '{}',
            chain TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL,
            result TEXT, error TEXT,
            created REAL NOT NULL, started REAL, finished REAL, duration_ms INTEGER,
            log TEXT NOT NULL DEFAULT '[]', model TEXT NOT NULL DEFAULT '')""",
        "CREATE INDEX IF NOT EXISTS idx_tardis_created ON tardis_tasks(created)",
        """CREATE TABLE IF NOT EXISTS project_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'nota',
            text TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}',
            created REAL NOT NULL, source TEXT NOT NULL DEFAULT 'usuario')""",
        "CREATE INDEX IF NOT EXISTS idx_project_notes ON project_notes(project, created)",
    ]),
]


class Database:
    """Conexão SQLite compartilhada e protegida por lock (leituras e escritas curtas)."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False,
                                     isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        self.migrate()

    def migrate(self) -> int:
        with self._lock:
            self._conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            current = int(row[0] or 0)
            for version, statements in MIGRATIONS:
                if version <= current:
                    continue
                self._conn.execute("BEGIN")
                try:
                    for sql in statements:
                        self._conn.execute(sql)
                    self._conn.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
                    self._conn.execute("COMMIT")
                except Exception:
                    self._conn.execute("ROLLBACK")
                    raise
                current = version
            return current

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def integrity_ok(self) -> bool:
        try:
            row = self.one("PRAGMA quick_check")
            return bool(row) and str(row[0]).lower() == "ok"
        except sqlite3.Error:
            return False

    def size_bytes(self) -> int:
        try:
            return Path(self.path).stat().st_size
        except OSError:
            return 0

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return str(row["value"]) if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, str(value)))

    def audit(self, source: str, action: str, detail: Any, verified: bool | None = None) -> None:
        text = str(detail or "")[:400]
        if looks_secret(text):
            text = "[redigido: possível dado sensível]"
        verified_int = None if verified is None else int(bool(verified))
        with self._lock:
            self._conn.execute("INSERT INTO audit(source,action,detail,verified,created_at) VALUES(?,?,?,?,?)",
                               (str(source)[:40], str(action)[:80], text, verified_int, time.time()))
            self._conn.execute("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 2000)")

    def backup_to(self, destination: Path | str) -> Path:
        """Cópia consistente do banco inteiro com o JARVIS rodando (API de backup do SQLite: não
        copia um arquivo pela metade). O destino não pode existir — nada é sobrescrito."""
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(f"já existe: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        target = sqlite3.connect(str(partial))
        try:
            with self._lock:
                self._conn.backup(target)
            row = target.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise sqlite3.DatabaseError("a cópia não passou na verificação de integridade")
        finally:
            target.close()
        partial.replace(destination)
        return destination

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass


def verify_database_file(path: Path | str) -> tuple[bool, str]:
    """(íntegro?, detalhe) de um arquivo de banco — usado antes de restaurar um backup."""
    path = Path(path)
    if not path.is_file():
        return False, "arquivo não encontrado"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, f"não é um banco do JARVIS legível: {exc}"
    if not row or str(row[0]).lower() != "ok":
        return False, f"integridade comprometida: {row[0] if row else '?'}"
    return True, f"íntegro (esquema v{version[0] if version and version[0] is not None else '?'})"


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default
