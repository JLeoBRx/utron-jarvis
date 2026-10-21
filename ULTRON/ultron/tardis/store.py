"""Persistência da TARDIS no MESMO banco do JARVIS (migração v5): tarefas e memória de projeto.

Textos que parecem segredo (senhas, tokens, cartões) são redigidos antes de gravar — a memória de
projeto nunca guarda credenciais. Retenção das tarefas: as 2000 mais recentes.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..memory.store import looks_secret
from .protocol import TaskEnvelope, dumps

KEEP_TASKS = 2000
NOTE_KINDS = ("nota", "decisao", "parametro")
NOTE_LABELS = {"nota": "nota", "decisao": "decisão", "parametro": "parâmetro"}


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return "[redigido: possível dado sensível]" if looks_secret(value) else value
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class TardisStore:
    def __init__(self, db):
        self.db = db
        self._writes = 0

    # ------------------------------------------------------------ tarefas
    def save(self, envelope: TaskEnvelope) -> None:
        data = envelope.to_dict()
        self.db.execute(
            "INSERT INTO tardis_tasks(id,kind,origin,input,chain,state,result,error,created,started,finished,"
            "duration_ms,log,model) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "state=excluded.state, result=excluded.result, error=excluded.error, started=excluded.started, "
            "finished=excluded.finished, duration_ms=excluded.duration_ms, log=excluded.log, model=excluded.model",
            (data["id"], data["kind"], data["origin"], dumps(_redact(data["input"])), dumps(data["chain"]),
             data["state"], dumps(_redact(data["result"])) if data["result"] else None,
             dumps(data["error"]) if data["error"] else None, data["created"], data["started"], data["finished"],
             data["duration_ms"], dumps(data["log"]), data["model"]))
        self._writes += 1
        if self._writes % 100 == 0:
            self.db.execute("DELETE FROM tardis_tasks WHERE id IN (SELECT id FROM tardis_tasks ORDER BY created "
                            "DESC LIMIT -1 OFFSET ?)", (KEEP_TASKS,))

    @staticmethod
    def _row(row) -> TaskEnvelope:
        data = dict(row)
        for key in ("input", "chain", "result", "error", "log"):
            if data.get(key):
                try:
                    data[key] = json.loads(data[key])
                except ValueError:
                    data[key] = None
        return TaskEnvelope.from_dict(data)

    def get(self, task_id: str) -> TaskEnvelope | None:
        row = self.db.one("SELECT * FROM tardis_tasks WHERE id=?", (task_id,))
        return self._row(row) if row else None

    def recent(self, limit: int = 50, *, kind: str | None = None) -> list[TaskEnvelope]:
        if kind:
            rows = self.db.query("SELECT * FROM tardis_tasks WHERE kind=? ORDER BY created DESC LIMIT ?",
                                 (kind, int(limit)))
        else:
            rows = self.db.query("SELECT * FROM tardis_tasks ORDER BY created DESC LIMIT ?", (int(limit),))
        return [self._row(r) for r in rows]

    def interrupted(self) -> int:
        """Tarefas que estavam na fila ou rodando quando o JARVIS fechou: viram CANCELLED (com o motivo)."""
        cursor = self.db.execute("UPDATE tardis_tasks SET state='CANCELLED', error=? WHERE state IN "
                                 "('QUEUED','RUNNING')",
                                 (dumps({"code": "INTERRUPTED", "message": "o JARVIS foi encerrado antes do fim"}),))
        return max(0, cursor.rowcount or 0)

    # ------------------------------------------------------------ memória de projeto
    def add_note(self, text: str, *, project: str = "", kind: str = "nota", data: dict | None = None,
                 source: str = "usuario") -> int:
        text = " ".join(str(text or "").split())
        if not text:
            raise ValueError("nota vazia")
        if looks_secret(text):
            raise ValueError("a memória de projeto não guarda senhas, tokens ou dados sensíveis")
        if kind not in NOTE_KINDS:
            raise ValueError(f"tipo de nota inválido: {kind}")
        cursor = self.db.execute("INSERT INTO project_notes(project,kind,text,data,created,source) VALUES(?,?,?,?,?,?)",
                                 (str(project or "").strip()[:80], kind, text[:2000], dumps(_redact(data or {})),
                                  time.time(), source[:40]))
        return int(cursor.lastrowid)

    def notes(self, *, project: str | None = None, kind: str | None = None, search: str = "",
              limit: int = 50) -> list[dict]:
        where, params = [], []
        if project:
            where.append("project = ?")
            params.append(project)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        if search:
            where.append("(text LIKE ? OR project LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        sql = "SELECT * FROM project_notes" + (f" WHERE {' AND '.join(where)}" if where else "")
        rows = self.db.query(sql + " ORDER BY created DESC LIMIT ?", (*params, int(limit)))
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["data"] = json.loads(item.get("data") or "{}")
            except ValueError:
                item["data"] = {}
            item["kind_label"] = NOTE_LABELS.get(item["kind"], item["kind"])
            out.append(item)
        return out

    def projects(self) -> list[str]:
        return [r["project"] for r in self.db.query("SELECT DISTINCT project FROM project_notes WHERE project != '' "
                                                    "ORDER BY project")]
