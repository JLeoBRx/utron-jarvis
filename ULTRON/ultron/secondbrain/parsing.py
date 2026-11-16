"""Datas e horas em português, sem modelo: "amanhã às 18h", "sexta 9h30", "dia 12/10 às 14:00",
"daqui a 15 minutos", "toda segunda às 8h", "todo dia às 7h", "às 6 da tarde".

Devolve o horário de parede resolvido (o próximo instante compatível com a frase), se é só
data (dia inteiro), a recorrência, o trecho reconhecido e — quando a frase é ambígua — a
pergunta de esclarecimento. Nunca chuta uma hora ambígua: "às 3" pode ser 03:00 ou 15:00,
então a resposta é perguntar. Convenção brasileira: "8h"/"20h" são horas de 24 h.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field

WEEKDAYS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
MONTHS = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
          "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
NUMBERS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
           "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
           "quarenta": 40, "quarenta e cinco": 45, "meia": 0.5}
PERIODS = {"manha": (9, 0), "tarde": (15, 0), "noite": (20, 0), "madrugada": (3, 0)}


def fold(text: str) -> str:
    """Minúsculas sem acento, com o MESMO comprimento do texto original (posições valem nos dois)."""
    out = []
    for ch in str(text):
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base.lower() if len(base.lower()) == 1 else ch.lower()[:1])
    return "".join(out)


@dataclass
class When:
    wall: dt.datetime | None = None
    all_day: bool = False
    recurrence: str = ""                    # "" | daily | weekdays | weekly | monthly
    spans: list = field(default_factory=list)   # (início, fim) de cada trecho reconhecido
    ambiguous: str = ""                     # pergunta de esclarecimento ("" = não ambíguo)
    has_date: bool = False
    has_time: bool = False

    @property
    def found(self) -> bool:
        return self.has_date or self.has_time or bool(self.recurrence)

    def strip(self, text: str) -> str:
        """Texto sem os trechos de data/hora reconhecidos."""
        out, last = [], 0
        for start, end in sorted(self.spans):
            if start >= last:
                out.append(text[last:start])
                last = end
        out.append(text[last:])
        return " ".join("".join(out).split())


_NUM = r"(\d{1,3}|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|quinze|vinte|trinta|" \
       r"quarenta e cinco|quarenta|meia)"
RELATIVE_RE = re.compile(rf"\b(?:daqui a|daqui|em|dentro de)\s+{_NUM}\s*(minutos?|min|horas?|h|dias?|semanas?)\b")
HALF_HOUR_RE = re.compile(r"\b(?:daqui a|em|dentro de)\s+meia hora\b")
DAYWORD_RE = re.compile(r"\b(depois de amanha|amanha|hoje)\b")
TONIGHT_RE = re.compile(r"\b(esta|essa|hoje a) noite\b")
WEEKDAY_RE = re.compile(r"\b(?:(?:na|no|nesta|neste|nessa|nesse|esta|este|essa|esse|proxima|proximo|n[ao] proxim[ao])\s+)?"
                        r"(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira| feira)?(\s+que vem)?\b")
DATE_NUM_RE = re.compile(r"\b(?:dia\s+)?(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b")
DATE_TEXT_RE = re.compile(r"\b(?:dia\s+)?(\d{1,2})\s+de\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|"
                          r"setembro|outubro|novembro|dezembro)(?:\s+de\s+(\d{4}))?\b")
DAY_ONLY_RE = re.compile(r"\bdia\s+(\d{1,2})\b")
TIME_RE = re.compile(r"\b(?:as|a|para as|pelas|por volta das|ate as)?\s*(\d{1,2})(?:(?::|h)(\d{2})|\s*(h)(?:oras?)?\b|"
                     r"\s+horas?\b)?(?:\s+e\s+(meia|quinze|trinta|quarenta e cinco))?"
                     r"(?:\s+(?:da|de)\s+(manha|tarde|noite|madrugada))?")
NOON_RE = re.compile(r"\b(?:ao |as |a )?(meio[- ]dia|meia[- ]noite)(?:\s+e\s+meia)?\b")
PERIOD_RE = re.compile(r"\b(?:de|pela|a|na)\s+(manha|tarde|noite|madrugada)\b")
RECUR_RE = re.compile(r"\b(todo dia|todos os dias|diariamente|toda semana|semanalmente|todo mes|todos os meses|"
                      r"mensalmente|dias uteis|de segunda a sexta|tod[ao]s? (?:as |os )?"
                      r"(segunda|terca|quarta|quinta|sexta|sabado|domingo)s?(?:-feiras?)?)\b")


def _num(token: str) -> float:
    token = token.strip()
    if token.isdigit():
        return float(token)
    return float(NUMBERS.get(token, 0))


def _next_weekday(base: dt.date, weekday: int, *, force_next_week: bool) -> dt.date:
    days = (weekday - base.weekday()) % 7
    if force_next_week and days == 0:
        days = 7
    return base + dt.timedelta(days=days)


def parse(text: str, now: dt.datetime) -> When:
    """Interpreta datas/horas de ``text`` relativas a ``now`` (horário de parede)."""
    t = fold(text)
    when = When()
    date: dt.date | None = None
    hour = minute = None
    taken: list[tuple[int, int]] = []

    def take(match) -> None:
        when.spans.append((match.start(), match.end()))
        taken.append((match.start(), match.end()))

    def free(match) -> bool:
        return all(match.end() <= a or match.start() >= b for a, b in taken)

    # ---------------------------------------------------------------- recorrência
    recur = RECUR_RE.search(t)
    if recur:
        phrase = recur.group(1)
        if phrase in ("todo dia", "todos os dias", "diariamente"):
            when.recurrence = "daily"
        elif phrase in ("dias uteis", "de segunda a sexta"):
            when.recurrence = "weekdays"
        elif phrase in ("todo mes", "todos os meses", "mensalmente"):
            when.recurrence = "monthly"
        else:
            when.recurrence = "weekly"
            if recur.group(2):
                date = _next_weekday(now.date(), WEEKDAYS[recur.group(2)], force_next_week=False)
                when.has_date = True
        take(recur)
    # ---------------------------------------------------------------- relativo ("daqui a 15 minutos")
    half = HALF_HOUR_RE.search(t)
    rel = RELATIVE_RE.search(t)
    if half or rel:
        if half:
            delta = dt.timedelta(minutes=30)
            take(half)
        else:
            amount, unit = _num(rel.group(1)), rel.group(2)
            if unit.startswith("min"):
                delta = dt.timedelta(minutes=amount)
            elif unit.startswith("h"):
                delta = dt.timedelta(hours=amount)
            elif unit.startswith("semana"):
                delta = dt.timedelta(weeks=amount)
            else:
                delta = dt.timedelta(days=amount)
            take(rel)
        target = now + delta
        when.wall = target.replace(second=0, microsecond=0)
        when.has_date = when.has_time = True
        if rel is not None and not half and rel.group(2).startswith(("dia", "semana")):
            when.has_time = False                      # "daqui a 3 dias": dia, sem hora definida
            when.all_day = True
            when.wall = dt.datetime.combine(target.date(), dt.time(0, 0))
        return _finish(when, now)
    # ---------------------------------------------------------------- data
    tonight = TONIGHT_RE.search(t)
    if tonight and free(tonight):
        date, hour, minute = now.date(), 20, 0
        when.has_date = when.has_time = True
        take(tonight)
    for regex in (DATE_TEXT_RE, DATE_NUM_RE):
        match = regex.search(t)
        if match and free(match) and date is None:
            day = int(match.group(1))
            month = MONTHS[match.group(2)] if regex is DATE_TEXT_RE else int(match.group(2))
            year = match.group(3)
            year = int(year) + (2000 if year and len(year) == 2 else 0) if year else now.year
            try:
                candidate = dt.date(year, month, day)
            except ValueError:
                when.ambiguous = f"A data {day}/{month} não existe. Qual dia?"
                return when
            if not match.group(3) and candidate < now.date():
                try:
                    candidate = candidate.replace(year=year + 1)       # "12/01" em dezembro = ano que vem
                except ValueError:
                    pass
            date = candidate
            when.has_date = True
            take(match)
    if date is None:
        dayword = DAYWORD_RE.search(t)
        if dayword and free(dayword):
            offset = {"hoje": 0, "amanha": 1, "depois de amanha": 2}[dayword.group(1)]
            date = now.date() + dt.timedelta(days=offset)
            when.has_date = True
            take(dayword)
    if date is None:
        weekday = WEEKDAY_RE.search(t)
        if weekday and free(weekday):
            force = bool(weekday.group(2)) or "proxim" in weekday.group(0)
            date = _next_weekday(now.date(), WEEKDAYS[weekday.group(1)], force_next_week=force)
            when.has_date = True
            take(weekday)
    if date is None:
        day_only = DAY_ONLY_RE.search(t)
        if day_only and free(day_only):
            day = int(day_only.group(1))
            year, month = now.year, now.month
            if day < now.day:
                month += 1
                if month > 12:
                    year, month = year + 1, 1
            if not 1 <= day <= calendar.monthrange(year, month)[1]:
                when.ambiguous = f"O mês não tem dia {day}. Qual data?"
                return when
            date = dt.date(year, month, day)
            when.has_date = True
            take(day_only)
    # ---------------------------------------------------------------- hora
    noon = NOON_RE.search(t)
    if noon and free(noon):
        hour, minute = (12 if noon.group(1).startswith("meio") else 0), (30 if "e meia" in noon.group(0) else 0)
        when.has_time = True
        take(noon)
    if hour is None or when.has_time is False:
        for match in TIME_RE.finditer(t):
            if not match.group(1) or not free(match):
                continue
            prefix = match.group(0).strip()
            explicit_marker = bool(match.group(2) or match.group(3)) or "hora" in prefix
            has_prep = prefix[:1].isalpha() and not prefix.startswith(match.group(1))
            if not (explicit_marker or has_prep or match.group(5)):
                continue                                  # número solto ("2 relatórios"): não é hora
            h = int(match.group(1))
            m = int(match.group(2)) if match.group(2) else 0
            if match.group(4):
                m = {"meia": 30, "quinze": 15, "trinta": 30, "quarenta e cinco": 45}[match.group(4)]
            if h > 23 or m > 59:
                continue
            period = match.group(5)
            if period in ("tarde", "noite") and h < 12:
                h += 12
            elif period == "madrugada" and h == 12:
                h = 0
            elif not period and not (match.group(2) or match.group(3)) and 1 <= h <= 6:
                when.ambiguous = f"Às {h} da manhã ou às {h + 12}?"   # "às 3" sem "h" nem período: perguntar
            hour, minute = h, m
            when.has_time = True
            take(match)
            break
    if not when.has_time:
        for period in PERIOD_RE.finditer(t):
            if free(period):
                hour, minute = PERIODS[period.group(1)]
                when.has_time = True
                take(period)
                break
    # ---------------------------------------------------------------- composição
    if not (when.has_date or when.has_time):
        return when
    if when.has_time and date is None:
        date = now.date()
        if (hour, minute) <= (now.hour, now.minute) and not when.recurrence:
            date = date + dt.timedelta(days=1)            # "às 18h" depois das 18h = amanhã
    if when.has_time:
        when.wall = dt.datetime.combine(date, dt.time(hour, minute))
        if when.recurrence == "weekly" and when.wall <= now:
            when.wall += dt.timedelta(days=7)
        elif when.recurrence in ("daily", "weekdays") and when.wall <= now:
            when.wall += dt.timedelta(days=1)
            while when.recurrence == "weekdays" and when.wall.weekday() >= 5:
                when.wall += dt.timedelta(days=1)
    else:
        when.wall = dt.datetime.combine(date, dt.time(0, 0))
        when.all_day = True
    return _finish(when, now)


def _finish(when: When, now: dt.datetime) -> When:
    if when.wall is not None and when.has_time and when.wall < now - dt.timedelta(minutes=1) and not when.recurrence:
        when.ambiguous = when.ambiguous or "Esse horário já passou. Para quando?"
    return when
