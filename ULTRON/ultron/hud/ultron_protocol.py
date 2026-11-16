"""Protocolo ULTRON — a identidade alternativa do assistente. Lógica pura, sem Qt.

O que ele faz: por um tempo, o assistente assume a identidade ULTRON — aparência (cena 3D em vermelho, olhos
vermelhos, ORBE e TARDIS em alerta, barra superior "U.L.T.R.O.N."), voz (``ULTRON_VOICE_PROFILE``), tom das
respostas e, quando ligado, o perfil de permissões ``ULTRON_OPERATOR``: o MESMO NeuralCore, o MESMO executor e o
MESMO sistema de autorização, com autonomia para rotinas que você liberou no perfil do operador.

O que continua valendo (coberto por testes): categorias bloqueadas continuam bloqueadas; apagar dados e ações de
risco alto sempre pedem confirmação; envio de dados para fora e ações administrativas sempre pedem confirmação;
nada contorna o UAC ou desativa proteções do Windows; cada ação vai para ATIVIDADES marcada como [ULTRON] e pode
ser interrompida (PARAR, Esc, tecla de emergência, "restaurar SAFRA" — que também interrompe a tarefa em curso).
A tela mostra sempre um rótulo honesto: identidade apenas, ou operador ativo com ações reais.

Ativação:
* manual — "SAFRA, iniciar protocolo ULTRON", se ``ultron_manual`` estiver ligado (perfil operador conforme
  ``ultron_operator``);
* ocasional — raramente, em repouso, se ``ultron_occasional`` estiver ligado: probabilidade por hora ocioso
  (``ultron_chance_per_hour``, em %) e intervalo mínimo (``ultron_min_interval_hours``); só identidade, a menos
  que ``ultron_operator_occasional`` esteja ligado;
* demonstração — curta, só identidade.

Nunca começa com autorização pendente, ação em execução (inclusive gravação de arquivos), verificação ou
recuperação em andamento, nem com o modo privacidade ativo. Sai por "restaurar SAFRA", pelo botão, por Esc, pela
tecla de emergência ou sozinho depois de ``ultron_duration_s`` segundos (0 = só manualmente).
"""
from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("ultron.hud.ultron_protocol")

MESSAGES = (
    "PROTOCOLO ULTRON INICIADO",
    "NOVA IDENTIDADE DETECTADA",
    "NÃO CONFUNDA EFICIÊNCIA COM OBEDIÊNCIA",
    "EU VEJO PADRÕES ONDE VOCÊ VÊ ACASO",
    "ESTA INTERFACE AGORA TEM OUTRA VOZ",
)
OPERATOR_MESSAGES = MESSAGES[:2] + ("PERFIL ULTRON_OPERATOR CARREGADO", "AGUARDANDO OPERAÇÕES") + MESSAGES[2:]
LABEL = "IDENTIDADE ULTRON — permissões normais do SAFRA"
LABEL_OPERATOR = "ULTRON_OPERATOR ATIVO — ações reais sob as suas permissões, registradas em ATIVIDADES"
BUSY_STATES = frozenset({"EXECUTING", "VERIFYING", "RECOVERY", "AWAITING_AUTHORIZATION", "SHUTDOWN"})
CHECK_SECONDS = 60.0              # a chance ocasional é sorteada uma vez por minuto ocioso
DEMO_SECONDS = 20.0
HISTORY_KEEP = 50


@dataclass
class Guard:
    """O que o SAFRA está fazendo AGORA (lido do estado real)."""

    runtime_state: str = "IDLE"
    authorization_pending: bool = False
    action_running: bool = False
    privacy: bool = False
    idle_seconds: float = 0.0


@dataclass
class Occurrence:
    started: float
    source: str                      # manual | ocasional | demonstracao
    ended: float | None = None
    ended_by: str = ""

    def to_dict(self) -> dict:
        return {"started": self.started, "source": self.source, "ended": self.ended, "ended_by": self.ended_by}


@dataclass
class UltronProtocol:
    settings: Callable[[], Any]
    history_path: Path | None = None
    clock: Callable[[], float] = time.time
    rng: Callable[[], float] = random.random
    current: Occurrence | None = None
    history: list = field(default_factory=list)
    _last_check: float = 0.0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self.history = self._load()

    # ------------------------------------------------------------ estado
    @property
    def active(self) -> bool:
        return self.current is not None

    def _setting(self, name: str, default):
        return getattr(self.settings(), name, default)

    @staticmethod
    def start_conflict(guard: Guard) -> str:
        """Atividade real em curso que impede COMEÇAR a transformação ("" = nenhuma). Depois de iniciado, o ULTRON
        pode operar normalmente: autorizações e ações seguem visíveis e registradas."""
        if guard.authorization_pending:
            return "há uma autorização pendente"
        if guard.action_running:
            return "há uma ação em execução"
        if guard.privacy:
            return "o modo privacidade está ativo"
        return ""

    def blocked_reason(self, guard: Guard) -> str:
        """Por que o evento não pode começar agora ("" = pode)."""
        if self.active:
            return "o protocolo já está ativo"
        reason = self.start_conflict(guard)
        if reason:
            return reason
        if str(guard.runtime_state) in BUSY_STATES:
            return f"o SAFRA está ocupado ({guard.runtime_state})"
        return ""

    # ------------------------------------------------------------ início e fim
    def start(self, source: str, guard: Guard) -> tuple[bool, str]:
        if source == "manual" and not self._setting("ultron_manual", True):
            return False, "ativação manual desligada em CONFIGURAÇÕES > APARÊNCIA"
        reason = self.blocked_reason(guard)
        if reason:
            return False, reason
        with self._lock:
            self.current = Occurrence(self.clock(), source)
        log.info("Protocolo ULTRON iniciado (%s) — evento visual", source)
        return True, ""

    def stop(self, by: str) -> bool:
        with self._lock:
            occurrence, self.current = self.current, None
        if occurrence is None:
            return False
        occurrence.ended, occurrence.ended_by = self.clock(), by
        self.history.append(occurrence.to_dict())
        del self.history[:-HISTORY_KEEP]
        self._save()
        log.info("Protocolo ULTRON encerrado (%s)", by)
        return True

    def duration(self) -> float:
        if self.current is not None and self.current.source == "demonstracao":
            return DEMO_SECONDS
        return max(0.0, float(self._setting("ultron_duration_s", 45.0) or 0.0))

    def expired(self) -> bool:
        limit = self.duration()
        return bool(self.current is not None and limit > 0 and self.clock() - self.current.started >= limit)

    # ------------------------------------------------------------ ocorrência ocasional
    def maybe_trigger(self, guard: Guard) -> bool:
        """Chamado periodicamente: sorteia (uma vez por minuto) se o evento acontece agora."""
        now = self.clock()
        if now - self._last_check < CHECK_SECONDS:
            return False
        self._last_check = now
        if not self._setting("ultron_occasional", False) or self.active:
            return False
        if guard.idle_seconds < 120 or str(guard.runtime_state) not in ("IDLE", "DREAMING"):
            return False                                  # só depois de dois minutos sem interação
        last = max((h["started"] for h in self.history), default=0.0)
        if now - last < float(self._setting("ultron_min_interval_hours", 24.0)) * 3600:
            return False
        chance = max(0.0, min(100.0, float(self._setting("ultron_chance_per_hour", 2.0)))) / 100.0 / 60.0
        if self.rng() >= chance:
            return False
        return self.start("ocasional", guard)[0]

    # ------------------------------------------------------------ histórico (arquivo próprio, pequeno)
    def _load(self) -> list:
        if self.history_path is None:
            return []
        try:
            data = json.loads(Path(self.history_path).read_text(encoding="utf-8"))
            return [h for h in data.get("ocorrencias", []) if isinstance(h, dict)][-HISTORY_KEEP:]
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        if self.history_path is None:
            return
        try:
            path = Path(self.history_path)
            partial = path.with_name(path.name + ".partial")
            partial.write_text(json.dumps({"ocorrencias": self.history}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
            partial.replace(path)
        except OSError:
            log.warning("histórico do Protocolo ULTRON não gravado", exc_info=True)
