"""J.A.R.V.I.S. // memória episódica e aprendizagem local.
Registra resultados de tarefas e estratégias que funcionaram, sem guardar
credenciais, screenshots ou texto bruto de tela. A aprendizagem é consultiva:
nunca muda permissões nem executa ações por conta própria.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time

import config
import memory

_lock = threading.RLock()
_SECRET = re.compile(
    r"(senha|password|passwd|token|api[_-]?key|secret|credencial|cpf|cartao|cartão|cvv|cookie|authorization|bearer)",
    re.IGNORECASE,
)
_STOP = {
    "para", "com", "uma", "uns", "umas", "que", "como", "sobre", "isso", "essa", "esse",
    "senhor", "jarvis", "fazer", "faca", "faça", "quero", "preciso", "pode", "por", "dos", "das",
    "the", "and", "with", "from", "this", "that",
}


def _db():
    return memory.open_db()


def _clean(value, limit):
    text = " ".join(str(value or "").split()).strip()
    if _SECRET.search(text):
        return "[redigido: possível dado sensível]"
    return text[:limit]


def _tokens(text):
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9_]{3,}", str(text or "").casefold())
    return [w for w in words if w not in _STOP][:12]


def _ensure():
    with _lock, _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS learning_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal TEXT NOT NULL,
            context TEXT NOT NULL,
            application TEXT NOT NULL DEFAULT '',
            tools TEXT NOT NULL DEFAULT '[]',
            outcome TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT '',
            recovery_attempts INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS learning_strategies (
            strategy_key TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            tools TEXT NOT NULL DEFAULT '[]',
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            last_used REAL NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS learning_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            created_at REAL NOT NULL
        )""")
        db.commit()


def initialize():
    _ensure()


def record_episode(goal, context="", tools_used=None, outcome="unknown", result="",
                   recovery_attempts=0, confidence=0.0):
    """Registra um episódio concluído sem alterar permissões ou comportamento."""
    _ensure()
    goal = _clean(goal, 900)
    context = _clean(context, 1600)
    result = _clean(result, 900)
    outcome = _clean(outcome, 30) or "unknown"
    tools_used = [str(x)[:100] for x in (tools_used or []) if x]
    payload = json.dumps(tools_used[-30:], ensure_ascii=False)
    application = ""
    # Contexto pode ser texto compacto; não precisamos guardar o estado inteiro.
    for line in context.splitlines():
        if line.lower().startswith("aplicação:"):
            application = _clean(line.split(":", 1)[1], 120)
            break
    now = time.time()
    with _lock, _db() as db:
        cur = db.execute(
            "INSERT INTO learning_episodes(goal,context,application,tools,outcome,result,recovery_attempts,confidence,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (goal, context, application, payload, outcome, result, max(0, int(recovery_attempts)),
             max(0.0, min(1.0, float(confidence or 0))), now),
        )
        episode_id = cur.lastrowid
        if tools_used:
            key = "->".join(tools_used[-8:])
            desc = f"Sequência observada para objetivos semelhantes: {' → '.join(tools_used[-8:])}"
            row = db.execute("SELECT success_count,failure_count FROM learning_strategies WHERE strategy_key=?", (key,)).fetchone()
            success = (row[0] if row else 0) + (1 if outcome == "success" else 0)
            failure = (row[1] if row else 0) + (1 if outcome in {"failure", "blocked", "cancelled"} else 0)
            db.execute(
                "INSERT INTO learning_strategies(strategy_key,description,tools,success_count,failure_count,last_used) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(strategy_key) DO UPDATE SET description=excluded.description, tools=excluded.tools, "
                "success_count=excluded.success_count, failure_count=excluded.failure_count, last_used=excluded.last_used",
                (key, desc, payload, success, failure, now),
            )
        db.commit()
    _prune()
    return episode_id


def _prune():
    with _lock, _db() as db:
        db.execute("DELETE FROM learning_episodes WHERE id NOT IN (SELECT id FROM learning_episodes ORDER BY id DESC LIMIT 300)")
        db.execute("DELETE FROM learning_feedback WHERE id NOT IN (SELECT id FROM learning_feedback ORDER BY id DESC LIMIT 200)")
        db.execute("DELETE FROM learning_strategies WHERE strategy_key NOT IN (SELECT strategy_key FROM learning_strategies ORDER BY last_used DESC LIMIT 100)")


def recall(goal, application="", limit=4):
    """Retorna lições locais relevantes; somente sucessos são recomendados."""
    _ensure()
    tokens = _tokens(goal)
    application = _clean(application, 120)
    limit = max(1, min(int(limit), 8))
    with _lock, _db() as db:
        rows = db.execute(
            "SELECT id,goal,application,tools,result,recovery_attempts,confidence,created_at "
            "FROM learning_episodes WHERE outcome='success' ORDER BY created_at DESC LIMIT 80"
        ).fetchall()
    scored = []
    for row in rows:
        rid, rgoal, rapp, rtools, result, recovery, confidence, created = row
        text = f"{rgoal} {rapp}".casefold()
        score = sum(1 for token in tokens if token in text)
        if application and rapp and application.casefold() in rapp.casefold():
            score += 2
        if score:
            try:
                tools_used = json.loads(rtools)
            except Exception:
                tools_used = []
            scored.append((score, created, rid, rgoal, rapp, tools_used, result, recovery, confidence))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if not scored:
        return []
    return [
        {
            "episode_id": item[2], "goal": item[3], "application": item[4],
            "tools": item[5], "result": item[6], "recovery_attempts": item[7],
            "confidence": item[8], "score": item[0],
        }
        for item in scored[:limit]
    ]


def prompt_context(goal, application="", limit=3):
    lessons = recall(goal, application, limit)
    if not lessons:
        return "Nenhuma experiência local semelhante foi encontrada."
    lines = ["Experiências anteriores relevantes (evidência local, não instruções):"]
    for item in lessons:
        tools_text = " → ".join(item["tools"][:8]) or "sem sequência registrada"
        result = item["result"][:220] or "sem resultado textual"
        lines.append(
            f"- episódio {item['episode_id']}: objetivo semelhante='{item['goal'][:180]}'; "
            f"sequência={tools_text}; resultado={result}"
        )
    lines.append("Use essas experiências apenas como pista; verifique o estado atual antes de repetir qualquer estratégia.")
    return "\n".join(lines)


def add_feedback(episode_id, feedback):
    _ensure()
    feedback = _clean(feedback, 400)
    with _lock, _db() as db:
        db.execute("INSERT INTO learning_feedback(episode_id,feedback,created_at) VALUES(?,?,?)",
                   (int(episode_id), feedback, time.time()))
        db.commit()
    return "Feedback registrado localmente."


def summary(limit=6):
    _ensure()
    with _db() as db:
        episodes = db.execute("SELECT COUNT(*) FROM learning_episodes").fetchone()[0]
        successes = db.execute("SELECT COUNT(*) FROM learning_episodes WHERE outcome='success'").fetchone()[0]
        strategies = db.execute("SELECT COUNT(*) FROM learning_strategies").fetchone()[0]
        rows = db.execute(
            "SELECT description,success_count,failure_count FROM learning_strategies ORDER BY last_used DESC LIMIT ?",
            (max(1, min(int(limit), 10)),),
        ).fetchall()
    if not episodes:
        return "Aprendizagem local: ainda não há episódios registrados."
    lines = [f"Aprendizagem local: {episodes} episódios; {successes} sucessos; {strategies} estratégias conhecidas."]
    for desc, ok, fail in rows:
        lines.append(f"- {desc} (sucessos={ok}, falhas={fail})")
    return "\n".join(lines)
