"""Livro de consumo dos modelos — no MESMO banco SQLite (tabela ``model_usage``, migração v7).

Cada chamada a um modelo (local ou na nuvem) vira uma linha: quando, provedor, modelo, finalidade, rota,
tokens de entrada e saída, duração, se deu certo e o custo estimado. O custo só é calculado quando o preço do
modelo está configurado (CONFIGURAÇÕES > INTELIGÊNCIA, em US$ por milhão de tokens): o SAFRA não inventa
preços. Sem preço, o limite mensal vale em TOKENS (``cloud_monthly_token_limit``).

Nada do conteúdo das conversas é gravado aqui — só números e nomes de modelo.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Any, Callable

log = logging.getLogger("ultron.usage")


def _n(value: int) -> str:
    """1234567 → "1.234.567" (separador de milhar brasileiro)."""
    return f"{int(value):,}".replace(",", ".")


def month_start(now: float) -> float:
    day = dt.datetime.fromtimestamp(now)
    return dt.datetime(day.year, day.month, 1).timestamp()


def price_for(settings, target: str) -> tuple[float, float]:
    """(entrada, saída) em US$ por milhão de tokens para o alvo da nuvem; 0 = preço não configurado."""
    kind = "fast" if target == "cloud_fast" else "robust"
    return (float(getattr(settings, f"cloud_price_{kind}_in", 0.0) or 0.0),
            float(getattr(settings, f"cloud_price_{kind}_out", 0.0) or 0.0))


def estimate_cost(settings, target: str, input_tokens: int, output_tokens: int) -> float | None:
    price_in, price_out = price_for(settings, target)
    if price_in <= 0 and price_out <= 0:
        return None
    return (max(0, input_tokens) * price_in + max(0, output_tokens) * price_out) / 1_000_000


class UsageLedger:
    def __init__(self, db, *, settings_getter: Callable[[], Any], clock: Callable[[], float] = time.time):
        self.db = db
        self._settings = settings_getter
        self._clock = clock
        self._lock = threading.Lock()

    # ------------------------------------------------------------ escrita
    def record(self, *, provider: str, model: str, purpose: str = "", target: str = "", input_tokens: int = 0,
               output_tokens: int = 0, seconds: float = 0.0, ok: bool = True, detail: str = "") -> dict:
        paid = target in ("cloud_fast", "cloud_robust")
        cost = estimate_cost(self._settings(), target, input_tokens, output_tokens) if paid else 0.0
        row = {"at": self._clock(), "provider": provider, "model": model, "purpose": purpose, "target": target,
               "input_tokens": int(input_tokens or 0), "output_tokens": int(output_tokens or 0), "cost_usd": cost,
               "seconds": round(float(seconds or 0.0), 3), "ok": 1 if ok else 0, "detail": str(detail)[:200]}
        try:
            with self._lock:
                self.db.execute(
                    "INSERT INTO model_usage(at,provider,model,purpose,target,input_tokens,output_tokens,cost_usd,"
                    "seconds,ok,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (row["at"], provider, model, purpose, target, row["input_tokens"], row["output_tokens"], cost,
                     row["seconds"], row["ok"], row["detail"]))
        except Exception:                                  # o consumo nunca derruba uma resposta
            log.warning("consumo do modelo não registrado", exc_info=True)
        return row

    # ------------------------------------------------------------ leitura
    def month(self, now: float | None = None) -> dict:
        """Resumo do mês corrente: chamadas locais e na nuvem, tokens, custo (conhecido ou não)."""
        now = self._clock() if now is None else now
        start = month_start(now)
        rows = self.db.query(
            "SELECT target, COUNT(*) AS calls, SUM(input_tokens) AS tin, SUM(output_tokens) AS tout, "
            "SUM(COALESCE(cost_usd, 0)) AS cost, SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced, "
            "SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS failed FROM model_usage WHERE at >= ? GROUP BY target",
            (start,))
        out = {"since": start, "local_calls": 0, "cloud_calls": 0, "cloud_input_tokens": 0, "cloud_output_tokens": 0,
               "cloud_cost_usd": 0.0, "unpriced_calls": 0, "failed_calls": 0}
        for row in rows:
            paid = row["target"] in ("cloud_fast", "cloud_robust")
            out["failed_calls"] += int(row["failed"] or 0)
            if paid:
                out["cloud_calls"] += int(row["calls"] or 0)
                out["cloud_input_tokens"] += int(row["tin"] or 0)
                out["cloud_output_tokens"] += int(row["tout"] or 0)
                out["cloud_cost_usd"] += float(row["cost"] or 0.0)
                out["unpriced_calls"] += int(row["unpriced"] or 0)
            else:
                out["local_calls"] += int(row["calls"] or 0)
        out["cloud_cost_usd"] = round(out["cloud_cost_usd"], 6)
        out["cloud_tokens"] = out["cloud_input_tokens"] + out["cloud_output_tokens"]
        return out

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self.db.query("SELECT * FROM model_usage ORDER BY at DESC LIMIT ?", (int(limit),))
        return [dict(row) for row in rows]

    # ------------------------------------------------------------ limite mensal
    def budget(self, now: float | None = None) -> tuple[bool, str, dict]:
        """(dentro do limite?, motivo, resumo do mês). 0 nos limites = nenhum gasto na nuvem permitido."""
        s = self._settings()
        month = self.month(now)
        limit_usd = float(getattr(s, "cloud_monthly_limit_usd", 0.0) or 0.0)
        limit_tokens = int(getattr(s, "cloud_monthly_token_limit", 0) or 0)
        if limit_usd <= 0 or limit_tokens <= 0:
            return False, "limite mensal da nuvem em zero (CONFIGURAÇÕES > INTELIGÊNCIA)", month
        if month["cloud_cost_usd"] >= limit_usd:
            return False, (f"limite mensal de US$ {limit_usd:.2f} atingido (gasto estimado: "
                           f"US$ {month['cloud_cost_usd']:.2f})"), month
        if month["cloud_tokens"] >= limit_tokens:
            return False, f"limite mensal de {_n(limit_tokens)} tokens atingido", month
        return True, "", month


def describe_month(month: dict, settings) -> str:
    """Texto curto e honesto do consumo do mês (para a conversa, a voz e as configurações)."""
    cost = month.get("cloud_cost_usd", 0.0)
    unpriced = month.get("unpriced_calls", 0)
    parts = [f"{month.get('local_calls', 0)} chamada(s) a modelos locais (sem custo)",
             f"{month.get('cloud_calls', 0)} na nuvem, {_n(month.get('cloud_tokens', 0))} tokens"]
    if month.get("cloud_calls", 0):
        price = f"custo estimado US$ {cost:.4f}"
        if unpriced:
            price += f" ({unpriced} chamada(s) sem preço configurado — custo desconhecido)"
        parts.append(price)
    limit_usd = float(getattr(settings, "cloud_monthly_limit_usd", 0.0) or 0.0)
    limit_tokens = int(getattr(settings, "cloud_monthly_token_limit", 0) or 0)
    parts.append(f"limite: US$ {limit_usd:.2f} e {_n(limit_tokens)} tokens por mês")
    return "Neste mês: " + "; ".join(parts) + "."
