"""Comportamento do ULTRON: quando falar, quanto falar e como se dirigir ao usuário.

Separado da execução: estas regras nunca decidem *se* uma ação é executada, apenas
*como* o ULTRON se comunica sobre ela.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from . import dialogue


@dataclass
class BehaviorProfile:
    address_frequency: float = 0.25     # fração das falas que incluem "senhor"
    narrate_steps: bool = False         # não narra cada passo interno por voz
    speak_progress_after: float = 6.0   # só anuncia progresso em tarefas longas
    proactive_cooldown: float = 90.0    # intervalo mínimo entre interrupções proativas
    max_spoken_sentences: int = 3


@dataclass
class Behavior:
    profile: BehaviorProfile = field(default_factory=BehaviorProfile)
    _rng: random.Random = field(default_factory=lambda: random.Random(7))
    _last_proactive: float = 0.0

    def address(self, text: str) -> str:
        """Acrescenta 'senhor' ocasionalmente, sem repetição mecânica."""
        if not text or "senhor" in text.lower() or self._rng.random() > self.profile.address_frequency:
            return text
        if text.endswith("."):
            return text[:-1] + ", senhor."
        return text

    def acknowledge(self) -> str:
        return dialogue.say("ack")

    def should_announce_progress(self, elapsed: float) -> bool:
        return elapsed >= self.profile.speak_progress_after

    def may_interrupt(self, now: float | None = None) -> bool:
        """Política para falas proativas (o usuário não deve ser interrompido em excesso)."""
        now = time.time() if now is None else now
        if now - self._last_proactive < self.profile.proactive_cooldown:
            return False
        self._last_proactive = now
        return True

    def outcome_line(self, *, verified: bool | None, success: bool) -> str:
        if success and verified:
            return dialogue.say("done")
        if success and verified is None:
            return dialogue.say("done_unverified")
        return dialogue.say("failed")
