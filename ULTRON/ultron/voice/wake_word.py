"""Palavra de ativação "Jarvis".

O reconhecedor transcreve tudo; a ativação procura a palavra no INÍCIO da frase — no meio
de uma frase ela não ativa. Há três tipos de forma:

* **fortes**: "jarvis" e variantes que não são palavras comuns ("ja vis", "jar vis").
  Ativam sozinhas ("Jarvis.") ou seguidas de comando;
* **nomes** ("jarbas", "javi"): palavras do vocabulário do Vosk que soam como Jarvis mas são
  nomes próprios. Valem como fortes só quando abrem a frase; depois de "o", "ei"… exigem
  comando (evita "O Jarbas ligou" ativar o JARVIS);
* **fracas**: confusões medidas do reconhecedor com palavras comuns ("aviso", "aves",
  "a vez", "já vi", "davis"…). Só ativam seguidas de um comando reconhecido.

Medição (voz pt-BR sintetizada dizendo "Jarvis…", modelos instalados): o modelo pequeno
não tem "jarvis" no vocabulário; o grande tem "jarvis" e "jarbas", mas transcreve a palavra
como "aves", "aviso", "davis", "a vez". Gramática restrita foi testada e rejeitada: no
modelo grande toda frase vira "jarvis" (22 de 22 frases sem a palavra ativaram).
A calibração (``calibrate.py``) aprende as formas que o reconhecedor produz para a voz do
usuário. Após uma interação, uma janela de continuação permite falar sem repetir a palavra.
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


TARGET = "jarvis"
# Formas fortes padrão: "jarvis" e sequências incomuns que o reconhecedor produz para ela.
DEFAULT_STRONG_VARIANTS = ("jarvis", "javis", "ja vis", "jar vis", "jarvis jarvis")
# Nomes próprios do vocabulário do Vosk que soam como "Jarvis": fortes só no início da frase.
DEFAULT_NAME_VARIANTS = ("jarbas", "javi")
# Confusões medidas com palavras comuns ("Jarvis" → "aviso", "aves", "a vez"…). Exigem comando.
DEFAULT_WEAK_VARIANTS = ("aviso", "aves", "a vez", "ja vi", "e vi", "davis", "travis", "avis")
# Formas do ULTRON (identidade anterior), usadas só para migrar configurações salvas.
LEGACY_STRONG_VARIANTS = ("ultron", "ultrom", "ultrão", "ultrao", "últron", "ultrón", "altron", "ultro",
                          "ul tron", "u tron", "ultrone", "outron")
LEGACY_WEAK_VARIANTS = ("o tom", "o trom", "o tron", "u tom", "u trom", "ultra", "outro", "autor")


class WakeWordDetector:
    LEADING_FILLERS = {"ok", "ei", "hey", "oi", "ola", "e", "o", "ah", "hum", "fala"}

    def __init__(self, words: tuple = (TARGET,), variants: tuple = DEFAULT_STRONG_VARIANTS, *,
                 weak: tuple = DEFAULT_WEAK_VARIANTS,
                 names: tuple = DEFAULT_NAME_VARIANTS, followup_seconds: float = 12.0):
        self._lock = threading.Lock()
        self.followup_seconds = followup_seconds
        self._followup_until = 0.0
        self._names: set[str] = set()
        self.set_variants(words, variants, weak, names)

    def set_variants(self, words: tuple, variants: tuple, weak: tuple | None = None,
                     names: tuple | None = None) -> None:
        strong = {_norm(w) for w in tuple(words) + tuple(variants) if _norm(w)}
        with self._lock:
            if names is not None:
                self._names = {_norm(n) for n in names if _norm(n)} - strong
            weak_forms = {_norm(w) for w in (self._weak_set if weak is None else weak) if _norm(w)} - strong
            self._weak_set = tuple(sorted(weak_forms))
            # formas de várias palavras primeiro (casamento mais longo vence)
            self._forms = sorted([(f, "strong") for f in strong] + [(f, "name") for f in self._names] +
                                 [(f, "weak") for f in weak_forms - self._names],
                                 key=lambda item: (-len(item[0].split()), -len(item[0])))

    @property
    def forms(self) -> list[str]:
        with self._lock:
            return [f for f, kind in self._forms if kind in ("strong", "name")]

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
                    if kind == "name":                    # nome próprio: forte só abrindo a frase
                        kind = "strong" if start == 0 else "weak"
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


# Palavras comuns que nunca podem virar forma FORTE (ativariam o JARVIS em conversas normais).
_NEVER_VARIANTS = {"aviso", "avisos", "aves", "a vez", "vez", "vezes", "ja vi", "ja", "vi", "vis", "jovens", "jovem",
                   "javista", "jardim", "jantar", "janeiro", "janela", "jarra", "jogar", "davis", "travis", "avis",
                   "e vi", "ja vou", "garfo", "gravis", "jabes", "chaves", "javali", "harvard"}


def _close_to(candidate: str, target: str = TARGET) -> bool:
    import difflib
    return difflib.SequenceMatcher(None, candidate.replace(" ", ""), target).ratio() >= 0.6


def _candidate(transcript: str) -> str:
    words = _norm(transcript).split()
    if not words:
        return ""
    return " ".join(words[:2]) if len(words) >= 2 and len(words[0]) <= 3 else words[0]


def learn_variants(transcripts: list[str], known: tuple = ()) -> tuple:
    """Calibração: aprende como o reconhecedor ouve "Jarvis" na voz deste usuário.

    Só aceita como forma forte o que é próximo de "jarvis" e não é palavra comum.
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

    Uma forma fraca só ativa o JARVIS quando seguida de um comando reconhecido.
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
