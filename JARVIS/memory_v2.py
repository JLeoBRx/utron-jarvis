"""J.A.R.V.I.S. // MEMORY 2 (Fase 34)
Memória episódica e semântica com decaimento simples. Segredos são filtrados.
"""
from __future__ import annotations
import re, time, sqlite3
import memory

SECRET=re.compile(r"(senha|password|passwd|token|api[_-]?key|secret|credencial|cpf|cvv|cart[aã]o)",re.I)

def safe(text, limit=800):
    text=str(text or "").strip()
    return "" if not text or len(text)>limit or SECRET.search(text) else text

def init():
    with memory.open_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS episodic_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT, context TEXT, outcome TEXT, score REAL, created REAL)")
        db.execute("CREATE TABLE IF NOT EXISTS semantic_memory (key TEXT PRIMARY KEY, value TEXT, confidence REAL, updated REAL)")
        db.commit()

def remember_episode(goal, context, outcome, score=0.5):
    init(); goal=safe(goal,500); context=safe(context,700); outcome=safe(outcome,200)
    if not goal: return
    with memory.open_db() as db:
        db.execute("INSERT INTO episodic_memory(goal,context,outcome,score,created) VALUES(?,?,?,?,?)",(goal,context,outcome,max(0,min(1,float(score))),time.time()))
        db.execute("DELETE FROM episodic_memory WHERE id NOT IN (SELECT id FROM episodic_memory ORDER BY id DESC LIMIT 300)")
        db.commit()

def set_fact(key,value,confidence=0.7):
    init(); key=safe(key,180); value=safe(value,700)
    if not key or not value:return
    with memory.open_db() as db:
        db.execute("INSERT INTO semantic_memory(key,value,confidence,updated) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,confidence=excluded.confidence,updated=excluded.updated",(key,value,max(0,min(1,float(confidence))),time.time())); db.commit()

def recall(query,limit=5):
    init(); q="%"+str(query or "").split()[0][:40]+"%"
    with memory.open_db() as db:
        rows=db.execute("SELECT goal,context,outcome,score,created FROM episodic_memory WHERE goal LIKE ? ORDER BY score DESC,created DESC LIMIT ?",(q,max(1,min(10,int(limit))))).fetchall()
    return [{"goal":r[0],"context":r[1],"outcome":r[2],"score":r[3],"created":r[4]} for r in rows]

def decay(days=90):
    init(); cutoff=time.time()-max(1,int(days))*86400
    with memory.open_db() as db:
        db.execute("DELETE FROM episodic_memory WHERE created < ?",(cutoff,)); db.commit()
