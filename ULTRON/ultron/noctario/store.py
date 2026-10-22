"""Persistência do Noctário no MESMO banco do JARVIS (migração v6): voltas e operações.

Uma volta guarda as amostras da telemetria em colunas comprimidas (zlib): ~6 800 amostras de uma volta
de 5 min 40 s a 20 Hz ocupam dezenas de KB. Retenção: as 200 voltas e as 5 000 operações mais recentes.
O formato devolvido por ``runs()`` é o que a TARDIS analisa (``tardis/analyzers/telemetry.py``).
"""
from __future__ import annotations

import json
import time
import zlib

KEEP_RUNS = 200
KEEP_OPS = 5000
COLUMNS = ("t", "error", "corr", "pwm_l", "pwm_r", "lost", "cross", "pos")


def pack(samples: list[dict]) -> bytes:
    columns = {key: [s.get(key) for s in samples] for key in COLUMNS}
    return zlib.compress(json.dumps(columns, separators=(",", ":")).encode("utf-8"), 6)


def unpack(blob: bytes | None) -> list[dict]:
    if not blob:
        return []
    columns = json.loads(zlib.decompress(blob).decode("utf-8"))
    count = len(columns.get("t") or [])
    return [{key: columns[key][i] for key in COLUMNS if key in columns} for i in range(count)]


class NoctarioStore:
    def __init__(self, db):
        self.db = db
        self._writes = 0

    def save_run(self, run: dict) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO noctario_runs(id,started,finished,duration_s,result,source,params,crossings,"
            "losses,samples,summary) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (run["id"], run["started"], run.get("finished"), run.get("duration_s"), run["result"], run["source"],
             json.dumps(run.get("params") or {}), json.dumps(run.get("crossings") or []), int(run.get("losses") or 0),
             pack(run.get("samples") or []), json.dumps(run.get("summary") or {}, ensure_ascii=False)))
        self.db.execute("DELETE FROM noctario_runs WHERE id IN (SELECT id FROM noctario_runs ORDER BY started DESC "
                        "LIMIT -1 OFFSET ?)", (KEEP_RUNS,))

    def runs(self, limit: int = 10, *, samples: bool = True) -> list[dict]:
        """Mais recentes primeiro, no formato da análise de telemetria da TARDIS."""
        rows = self.db.query("SELECT * FROM noctario_runs ORDER BY started DESC LIMIT ?", (int(limit),))
        out = []
        for row in rows:
            params = json.loads(row["params"] or "{}")
            out.append({"id": row["id"], "started": row["started"], "finished": row["finished"],
                        "duration_s": row["duration_s"], "result": row["result"], "source": row["source"],
                        "params": {**params, "base_pwm": params.get("base"), "max_pwm": params.get("max"),
                                   "error_range": 3500},
                        "crossings": json.loads(row["crossings"] or "[]"), "losses": row["losses"],
                        "summary": json.loads(row["summary"] or "{}"),
                        "samples": unpack(row["samples"]) if samples else []})
        return out

    def record_op(self, *, seq: int | None, verb: str, args: dict, origin: str, requested: str, outcome: str,
                  detail: str = "", latency_ms: float | None = None, source: str = "robo") -> None:
        self.db.execute("INSERT INTO noctario_ops(at,seq,verb,args,origin,requested,outcome,detail,latency_ms,source) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (time.time(), seq, verb, json.dumps(args or {}), origin[:40], requested[:40], outcome,
                         detail[:300], latency_ms, source))
        self._writes += 1
        if self._writes % 200 == 0:
            self.db.execute("DELETE FROM noctario_ops WHERE id IN (SELECT id FROM noctario_ops ORDER BY id DESC "
                            "LIMIT -1 OFFSET ?)", (KEEP_OPS,))

    def ops(self, limit: int = 50) -> list[dict]:
        rows = self.db.query("SELECT * FROM noctario_ops ORDER BY id DESC LIMIT ?", (int(limit),))
        return [{**dict(r), "args": json.loads(r["args"] or "{}")} for r in rows]
