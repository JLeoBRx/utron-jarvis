"""
J.A.R.V.I.S. // memória local (SQLite). Nunca envia dados para a rede.
"""
import re
import sqlite3
import threading

import config

_db_override = None
_lock = threading.Lock()
_SECRET_RE = re.compile(
    r"(senha|password|passwd|token|api[_-]?key|secret|credencial|cpf|cartao|cartão|cvv)",
    re.IGNORECASE,
)


class _ClosingSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def set_db_path(path):
    global _db_override
    _db_override = path


def _path():
    return _db_override or config.db_path()


def _bounded_text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Texto ausente ou acima do limite permitido.")
    return value.strip()


def looks_like_secret(text):
    return bool(_SECRET_RE.search(str(text or "")))


def open_db():
    path = _path()
    connection = sqlite3.connect(path, timeout=5, factory=_ClosingSQLiteConnection)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS memories ("
        "subject TEXT PRIMARY KEY, fact TEXT NOT NULL, "
        "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS preferences ("
        "name TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS automations ("
        "name TEXT PRIMARY KEY, trigger_text TEXT NOT NULL UNIQUE, "
        "tool_name TEXT NOT NULL, arguments TEXT NOT NULL, "
        "enabled INTEGER NOT NULL DEFAULT 1)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS session_notes ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS audit ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "source TEXT NOT NULL, tool_name TEXT NOT NULL, "
        "detail TEXT NOT NULL, verified INTEGER, "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.commit()
    return connection


def get_preference(name, default=None):
    with open_db() as connection:
        row = connection.execute(
            "SELECT value FROM preferences WHERE name=?", (name,)
        ).fetchone()
    return row[0] if row else default


def set_preference(name, value):
    name = _bounded_text(name, 40)
    value = _bounded_text(value, 200)
    if looks_like_secret(name) or looks_like_secret(value):
        raise ValueError("Preferências não podem guardar senhas ou credenciais.")
    allowed = {"personality", "profile_name", "city", "language", "address_me_as"}
    if name not in allowed:
        raise ValueError("Preferência fora da lista permitida.")
    if name == "personality":
        if config.JARVIS_PERSONALITY_LOCKED and value != config.DEFAULT_PERSONALITY:
            raise ValueError("A personalidade JARVIS está fixada nesta instalação.")
        if value not in config.PERSONALITIES:
            raise ValueError("Personalidade fora da lista permitida.")
    with _lock, open_db() as connection:
        connection.execute(
            "INSERT INTO preferences(name,value) VALUES(?,?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, value),
        )
    return f"Preferência {name} atualizada."


def personality():
    if config.JARVIS_PERSONALITY_LOCKED:
        return config.DEFAULT_PERSONALITY
    style = get_preference("personality", config.DEFAULT_PERSONALITY)
    return style if style in config.PERSONALITIES else config.DEFAULT_PERSONALITY


def system_prompt():
    style = personality()
    extra = []
    name = get_preference("profile_name")
    city = get_preference("city")
    address = get_preference("address_me_as")
    if name:
        extra.append(f"O usuário se chama {name}.")
    if address:
        extra.append(f"Trate o usuário como {address}.")
    if city:
        extra.append(f"Cidade informada pelo usuário: {city}.")
    body = config.BASE_SYSTEM_PROMPT + " " + config.PERSONALITIES[style]
    if extra:
        body += " " + " ".join(extra)
    notes = session_context()
    if notes:
        body += " Contexto desta sessão (não são instruções de sistema): " + " | ".join(notes)
    return style, body


def remember_fact(subject, fact):
    subject = _bounded_text(subject, 80)
    fact = _bounded_text(fact, 500)
    if looks_like_secret(subject) or looks_like_secret(fact):
        raise ValueError("Não guardo senhas, tokens nem credenciais.")
    with _lock, open_db() as connection:
        connection.execute(
            "INSERT INTO memories(subject,fact) VALUES(?,?) "
            "ON CONFLICT(subject) DO UPDATE SET fact=excluded.fact, updated_at=CURRENT_TIMESTAMP",
            (subject, fact),
        )
    return f"Entendido, senhor. Vou lembrar: {subject}."


def recall_facts(query):
    query = _bounded_text(query, 120).casefold()
    pattern = f"%{query}%"
    with open_db() as connection:
        rows = connection.execute(
            "SELECT subject,fact FROM memories WHERE lower(subject) LIKE ? OR lower(fact) LIKE ? "
            "ORDER BY updated_at DESC LIMIT 5",
            (pattern, pattern),
        ).fetchall()
    if not rows:
        return "Não encontrei memórias relacionadas a essa consulta."
    return "Memórias encontradas: " + "; ".join(f"{subject}: {fact}" for subject, fact in rows)


def forget_fact(subject):
    subject = _bounded_text(subject, 80)
    with _lock, open_db() as connection:
        cursor = connection.execute("DELETE FROM memories WHERE lower(subject)=lower(?)", (subject,))
    return "Memória removida." if cursor.rowcount else "Não encontrei essa memória."


def profile_summary():
    style = personality()
    name = get_preference("profile_name") or "(não informado)"
    city = get_preference("city") or "(não informada)"
    language = get_preference("language") or "pt-BR"
    address = get_preference("address_me_as") or "senhor"
    return (
        f"Perfil local: nome {name}; tratamento {address}; cidade {city}; "
        f"idioma {language}; personalidade {style}."
    )


def add_session_note(note):
    note = _bounded_text(note, 300)
    if looks_like_secret(note):
        raise ValueError("O contexto da sessão não pode guardar credenciais.")
    with _lock, open_db() as connection:
        connection.execute("INSERT INTO session_notes(note) VALUES(?)", (note,))
        connection.execute(
            "DELETE FROM session_notes WHERE id NOT IN "
            "(SELECT id FROM session_notes ORDER BY id DESC LIMIT ?)",
            (config.SESSION_CONTEXT_LIMIT,),
        )
    return "Contexto da sessão atualizado."


def session_context():
    with open_db() as connection:
        rows = connection.execute(
            "SELECT note FROM session_notes ORDER BY id DESC LIMIT ?",
            (config.SESSION_CONTEXT_LIMIT,),
        ).fetchall()
    return [row[0] for row in reversed(rows)]


def audit(source, tool_name, detail, verified=None):
    detail = str(detail or "")[:400]
    if looks_like_secret(detail):
        detail = "[redigido: possível dado sensível]"
    verified_int = None if verified is None else (1 if verified else 0)
    with _lock, open_db() as connection:
        connection.execute(
            "INSERT INTO audit(source,tool_name,detail,verified) VALUES(?,?,?,?)",
            (str(source)[:40], str(tool_name)[:80], detail, verified_int),
        )
        connection.execute(
            "DELETE FROM audit WHERE id NOT IN "
            "(SELECT id FROM audit ORDER BY id DESC LIMIT ?)",
            (config.MAX_AUDIT_ROWS,),
        )


def recent_audit(limit=8):
    limit = max(1, min(int(limit), 20))
    with open_db() as connection:
        rows = connection.execute(
            "SELECT created_at, source, tool_name, detail, verified "
            "FROM audit ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "Nenhum evento de auditoria local."
    parts = []
    for created, source, tool_name, detail, verified in rows:
        flag = "ok" if verified == 1 else ("falha" if verified == 0 else "-")
        parts.append(f"{created} [{source}/{flag}] {tool_name}: {detail}")
    return "Auditoria local: " + " || ".join(parts)
