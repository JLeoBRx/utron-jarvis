"""Tempo do Second Brain: horário de parede local ↔ instante absoluto, com fuso explícito.

Regras:

* tudo é persistido duas vezes: o horário de parede pedido pelo usuário (``YYYY-MM-DD HH:MM``)
  e o instante absoluto calculado (epoch UTC). A recorrência anda no horário de PAREDE, então
  "todo dia às 8h" continua às 8h depois de uma mudança de horário de verão;
* fuso vazio = fuso do sistema operacional (inclui as regras de horário de verão do próprio
  Windows); um nome IANA (``America/Sao_Paulo``) usa ``zoneinfo`` — no Windows isso exige o
  pacote ``tzdata`` (incluído no requirements);
* horário inexistente (salto do horário de verão) avança para o primeiro instante válido;
  horário repetido (volta do horário de verão) usa a primeira ocorrência.
"""
from __future__ import annotations

import calendar
import datetime as dt
import time
from functools import lru_cache

WALL_FMT = "%Y-%m-%d %H:%M"


@lru_cache(maxsize=32)
def zone(name: str):
    """``tzinfo`` do nome IANA, ou ``None`` (fuso do sistema) quando vazio/indisponível."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return None


def to_epoch(wall: dt.datetime, tz_name: str = "") -> float:
    """Horário de parede (ingênuo) → instante absoluto."""
    tz = zone(tz_name)
    if tz is None:
        return float(time.mktime(wall.replace(tzinfo=None).timetuple()))     # regras do sistema (DST incluso)
    aware = wall.replace(tzinfo=tz, fold=0)
    epoch = aware.timestamp()
    # salto do horário de verão: um horário inexistente vira o primeiro instante válido depois dele
    back = dt.datetime.fromtimestamp(epoch, tz).replace(tzinfo=None)
    if back.replace(second=0, microsecond=0) < wall.replace(second=0, microsecond=0):
        epoch += (wall - back).total_seconds()
    return float(epoch)


def from_epoch(epoch: float, tz_name: str = "") -> dt.datetime:
    """Instante absoluto → horário de parede (ingênuo) no fuso escolhido."""
    tz = zone(tz_name)
    if tz is None:
        return dt.datetime.fromtimestamp(epoch)
    return dt.datetime.fromtimestamp(epoch, tz).replace(tzinfo=None)


def now_wall(tz_name: str = "", *, clock=time.time) -> dt.datetime:
    return from_epoch(clock(), tz_name)


def parse_wall(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, WALL_FMT)


def format_wall(value: dt.datetime) -> str:
    return value.strftime(WALL_FMT)


def add_months(value: dt.datetime, months: int, *, day: int | None = None) -> dt.datetime:
    """Soma meses mantendo o dia pedido (31 → último dia de meses curtos)."""
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    wanted = day or value.day
    last = calendar.monthrange(year, month)[1]
    return value.replace(year=year, month=month, day=min(wanted, last))


RECURRENCES = ("", "daily", "weekdays", "weekly", "monthly")


def next_occurrence(wall: dt.datetime, recurrence: str, *, after: dt.datetime, anchor_day: int | None = None
                    ) -> dt.datetime | None:
    """Próxima ocorrência (horário de parede) estritamente depois de ``after``."""
    if recurrence not in RECURRENCES or not recurrence:
        return None
    current = wall
    for _ in range(4000):                            # limite de segurança: nunca laço infinito
        if current > after:
            return current
        if recurrence == "daily":
            current = current + dt.timedelta(days=1)
        elif recurrence == "weekdays":
            current = current + dt.timedelta(days=1)
            while current.weekday() >= 5:
                current = current + dt.timedelta(days=1)
        elif recurrence == "weekly":
            current = current + dt.timedelta(days=7)
        elif recurrence == "monthly":
            current = add_months(current, 1, day=anchor_day or wall.day)
    return None


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def describe(wall: dt.datetime, *, all_day: bool = False, now: dt.datetime | None = None) -> str:
    """Texto curto e humano: "hoje às 18:00", "amanhã", "sexta-feira, 16/10 às 09:30"."""
    now = now or dt.datetime.now()
    days = (wall.date() - now.date()).days
    when = {0: "hoje", 1: "amanhã", -1: "ontem"}.get(days)
    if when is None:
        when = f"{DIAS[wall.weekday()]}, {wall:%d/%m}" if -7 < days < 7 else f"{wall:%d/%m/%Y}"
    return when if all_day else f"{when} às {wall:%H:%M}"
