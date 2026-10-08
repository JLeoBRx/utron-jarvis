"""J.A.R.V.I.S. // MEMORY ENGINE
Memória operacional: fatos, preferências, estratégias e resultados úteis.
Não guarda segredos nem transforma histórico bruto em instruções.
"""
from __future__ import annotations
import re, time, uuid
import memory

_SECRET = re.compile(r"(senha|password|passwd|token|api[_-]?key|secret|credencial|cpf|cart[aã]o|cvv)", re.I)


def _safe(text: str, limit: int = 700) -> str:
    text = str(text or "").strip()
    if not text or len(text) > limit or _SECRET.search(text):
        return ""
    return text


def init():
    with memory.open_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            context TEXT NOT NULL,
            strategy TEXT NOT NULL,
            outcome TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.5,
            uses INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fingerprint, strategy)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal TEXT NOT NULL,
            route TEXT NOT NULL,
            outcome TEXT NOT NULL,
            evidence TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.commit()


def _fingerprint(goal: str) -> str:
    text = re.sub(r"\d+", "#", str(goal or "").casefold())
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    words = [w for w in text.split() if len(w) > 2]
    return " ".join(words[:18])[:180] or "generic"


def record_episode(goal, route, outcome, evidence=""):
    init()
    goal = _safe(goal, 500); route = _safe(route, 40) or "unknown"
    outcome = _safe(outcome, 80) or "unknown"; evidence = _safe(evidence, 600)
    if not goal:
        return
    with memory.open_db() as db:
        db.execute("INSERT INTO episodes(goal,route,outcome,evidence) VALUES(?,?,?,?)",
                   (goal, route, outcome, evidence))
        db.execute("DELETE FROM episodes WHERE id NOT IN (SELECT id FROM episodes ORDER BY id DESC LIMIT 200)")
        db.commit()


def record_strategy(goal, context, strategy, outcome, score):
    init()
    fingerprint = _fingerprint(goal)
    context = _safe(context, 500) or "contexto não registrado"
    strategy = _safe(strategy, 500)
    outcome = _safe(outcome, 80) or "unknown"
    if not strategy:
        return
    score = max(0.0, min(1.0, float(score)))
    with memory.open_db() as db:
        row = db.execute("SELECT score,uses FROM learned_patterns WHERE fingerprint=? AND strategy=?",
                         (fingerprint, strategy)).fetchone()
        if row:
            old, uses = row
            new_score = (old * uses + score) / (uses + 1)
            db.execute("UPDATE learned_patterns SET context=?, outcome=?, score=?, uses=?, updated_at=CURRENT_TIMESTAMP WHERE fingerprint=? AND strategy=?",
                       (context, outcome, new_score, uses + 1, fingerprint, strategy))
        else:
            db.execute("INSERT INTO learned_patterns(fingerprint,context,strategy,outcome,score) VALUES(?,?,?,?,?)",
                       (fingerprint, context, strategy, outcome, score))
        db.commit()


def recall_strategies(goal, limit=3):
    init(); fingerprint = _fingerprint(goal)
    with memory.open_db() as db:
        rows = db.execute("SELECT strategy,outcome,score,uses FROM learned_patterns WHERE fingerprint=? ORDER BY score DESC, uses DESC LIMIT ?",
                          (fingerprint, max(1, min(5, int(limit))))).fetchall()
    return [{"strategy": r[0], "outcome": r[1], "score": r[2], "uses": r[3]} for r in rows]


def relevant_context(goal, limit=3):
    items = recall_strategies(goal, limit)
    if not items:
        return "Nenhuma estratégia aprendida relevante para este objetivo."
    return "Estratégias aprendidas relevantes: " + " | ".join(
        f"{x['strategy']} (resultado={x['outcome']}, confiança={x['score']:.2f}, usos={x['uses']})" for x in items
    )


def compact_summary(limit=8):
    init()
    with memory.open_db() as db:
        rows = db.execute("SELECT goal,outcome,route FROM episodes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return "Sem episódios operacionais registrados."
    return "Últimos episódios: " + " | ".join(f"{g[:90]} [{o}/{r}]" for g,o,r in rows)
