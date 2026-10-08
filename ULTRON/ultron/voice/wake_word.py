"""Palavra de ativação "Ultron".

O reconhecedor transcreve tudo; a ativação procura a palavra no INÍCIO da frase — no meio
de uma frase ela não ativa. Há dois níveis de forma:

* **fortes**: "ultron" e variantes que não são palavras comuns ("ultrom", "ul tron"...).
  Ativam sozinhas ("Ultron.") ou seguidas de comando;
* **fracas**: confusões medidas do reconhecedor com palavras comuns ("o tom", "outro",
  "ultra"...). Só ativam quando seguidas de um comando reconhecido — sozinhas, seriam
  falsos positivos em conversas normais.

Reconhecimento por gramática restrita (só "ultron") foi testado e rejeitado: o modelo
transforma qualquer fala em "ultron". A calibração (``calibrate.py``) aprende as formas
que o reconhecedor produz para a voz do usuário. Após uma interação, uma janela de
continuação permite falar sem repetir a palavra.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from dataclasses import dataclass


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


@dataclass
class WakeResult:
    detected: bool
    command: str = ""
    matched: str = ""
    strength: str = ""            # strong | weak


# Confusões medidas do modelo pt-fb para "Ultron" (fala sintetizada pt-BR: "o tom abra…")
# e formas foneticamente vizinhas no léxico do modelo (u w t r õ). Exigem comando.
DEFAULT_WEAK_VARIANTS = ("o tom", "o trom", "o tron", "u tom", "u trom", "ultra", "outro", "autor")


class WakeWordDetector:
    LEADING_FILLERS = {"ok", "ei", "hey", "oi", "ola", "e", "o", "ah", "hum"}

    def __init__(self, words: tuple = ("ultron",), variants: tuple = (), *, weak: tuple = DEFAULT_WEAK_VARIANTS,
                 followup_seconds: float = 12.0):
        self._lock = threading.Lock()
        self.followup_seconds = followup_seconds
        self._followup_until = 0.0
        self.set_variants(words, variants, weak)

    def set_variants(self, words: tuple, variants: tuple, weak: tuple | None = None) -> None:
        strong = {_norm(w) for w in tuple(words) + tuple(variants) if _norm(w)}
        with self._lock:
            weak_forms = {_norm(w) for w in (self._weak_set if weak is None else weak) if _norm(w)} - strong
            self._weak_set = tuple(sorted(weak_forms))
            # formas de várias palavras primeiro (casamento mais longo vence)
            self._forms = sorted([(f, "strong") for f in strong] + [(f, "weak") for f in weak_forms],
                                 key=lambda item: (-len(item[0].split()), -len(item[0])))

    @property
    def forms(self) -> list[str]:
        with self._lock:
            return [f for f, kind in self._forms if kind == "strong"]

    @property
    def weak_forms(self) -> list[str]:
        with self._lock:
            return [f for f, kind in self._forms if kind == "weak"]

    def detect(self, text: str) -> WakeResult:
        words = _norm(text).split()
        if not words:
            return WakeResult(False)
        raw_words = str(text).split()
        aligned = len(raw_words) == len(words)            # preserva a grafia original do comando
        with self._lock:
            forms = list(self._forms)
        for start in range(0, 3):
            if start >= len(words) or (start > 0 and words[start - 1] not in self.LEADING_FILLERS):
                break
            for form, kind in forms:
                parts = form.split()
                if words[start:start + len(parts)] == parts:
                    rest = (raw_words if aligned else words)[start + len(parts):]
                    command = " ".join(rest).strip(" ,;:.-")
                    return WakeResult(True, command, form, kind)
        return WakeResult(False)

    # ------------------------------------------------------------ janela de continuação
    def open_followup(self, seconds: float | None = None) -> None:
        with self._lock:
            self._followup_until = time.monotonic() + (self.followup_seconds if seconds is None else seconds)

    def close_followup(self) -> None:
        with self._lock:
            self._followup_until = 0.0

    def in_followup(self) -> bool:
        with self._lock:
            return time.monotonic() <= self._followup_until

    def followup_remaining(self) -> float:
        with self._lock:
            return max(0.0, self._followup_until - time.monotonic())


# Palavras comuns que nunca podem virar variante (ativariam o ULTRON em conversas normais).
_NEVER_VARIANTS = {"outro", "outra", "outros", "outras", "ultimo", "ultima", "alto", "alta", "altura", "ontem",
                   "entao", "entre", "ultra", "dentro", "centro", "tron", "trono", "sultao", "voltou", "volta"}


def _close_to(candidate: str, target: str = "ultron") -> bool:
    import difflib
    return difflib.SequenceMatcher(None, candidate.replace(" ", ""), target).ratio() >= 0.6


def _candidate(transcript: str) -> str:
    words = _norm(transcript).split()
    if not words:
        return ""
    return " ".join(words[:2]) if len(words) >= 2 and len(words[0]) <= 3 else words[0]


def learn_variants(transcripts: list[str], known: tuple = ()) -> tuple:
    """Calibração: aprende como o reconhecedor ouve "Ultron" na voz deste usuário.

    Só aceita como forma forte o que é próximo de "ultron" e não é palavra comum.
    """
    learned = list(known)
    for transcript in transcripts:
        candidate = _candidate(transcript)
        if (candidate and candidate not in learned and len(candidate) >= 3
                and candidate not in _NEVER_VARIANTS and _close_to(candidate)):
            learned.append(candidate)
    return tuple(learned)


def learn_weak_variants(transcripts: list[str], strong: tuple, known_weak: tuple = ()) -> tuple:
    """Formas fracas: confusões CONSISTENTES (2+ amostras) que não viraram forma forte.

    Uma forma fraca só ativa o ULTRON quando seguida de um comando reconhecido.
    """
    counts: dict[str, int] = {}
    for transcript in transcripts:
        candidate = _candidate(transcript)
        if candidate and candidate not in strong and len(candidate.replace(" ", "")) >= 3:
            counts[candidate] = counts.get(candidate, 0) + 1
    learned = list(known_weak)
    for candidate, count in counts.items():
        if count >= 2 and candidate not in learned:
            learned.append(candidate)
    return tuple(learned)
