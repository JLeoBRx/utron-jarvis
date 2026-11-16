"""Persona ativa do assistente: SAFRA (padrão) ou ULTRON (identidade alternativa do Protocolo ULTRON).

É UM processo, UM NeuralCore, UMA memória: a persona só muda a apresentação (aparência, voz, tom das respostas)
e, com o perfil ``ULTRON_OPERATOR``, a POLÍTICA de autonomia aplicada ao MESMO executor (ver
``agent/permissions.py``). Quem muda a persona é o Protocolo ULTRON (interface ou console); quem lê são a voz,
a personalidade, as permissões, o histórico de atividades, a cena 3D e a ORBE remota (pelo estado do núcleo).
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass

JARVIS, ULTRON = "jarvis", "ultron"
OPERATOR_PROFILE = "ULTRON_OPERATOR"


@dataclass(frozen=True)
class Persona:
    name: str = JARVIS
    operator: bool = False          # perfil ULTRON_OPERATOR em vigor (autonomia para rotinas autorizadas)
    since: float = 0.0
    source: str = ""                # manual | ocasional | demonstracao | console | ...

    @property
    def ultron(self) -> bool:
        return self.name == ULTRON

    @property
    def label(self) -> str:
        if not self.ultron:
            return "SAFRA"
        return f"U.L.T.R.O.N. · {OPERATOR_PROFILE}" if self.operator else "U.L.T.R.O.N."

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label, "profile": OPERATOR_PROFILE if self.operator else ""}


_lock = threading.Lock()
_current = Persona()


def current() -> Persona:
    with _lock:
        return _current


def set_persona(name: str, *, operator: bool = False, source: str = "") -> Persona:
    """Troca a persona (process-wide). ``operator`` só vale para o ULTRON."""
    global _current
    name = ULTRON if name == ULTRON else JARVIS
    with _lock:
        _current = Persona(name, bool(operator) and name == ULTRON, time.time(), source)
        return _current


def reset() -> Persona:
    return set_persona(JARVIS, source="reset")
