"""Os 12 estados do avatar, resolvidos a partir de SINAIS REAIS (função pura, sem Qt).

Prioridade (ARQUITETURA_ULTIMATE.md §7), da maior para a menor:

 1. Modo de privacidade        — modo privacidade ativo (microfone fechado)
 2. Erro de integração         — componente falhou, modelo indisponível, link do Noctário perdido sem pedido,
                                 ``runtime_state=ERROR`` (janela de 8 s)
 3. Aguardando confirmação     — autorização pendente
 4. Falando                    — áudio da fala saindo agora (posição real de reprodução)
 5. Apresentando alerta        — lembrete devido, alerta do Noctário, aviso de saúde (janela de 6 s); também
                                 TINGE os estados de prioridade menor
 6. Reconhecendo a fala        — parciais do reconhecimento nos últimos 0,8 s com a escuta aberta
 7. Escutando                  — escuta aberta (palavra de ativação ou continuação)
 8. Consultando a TARDIS       — tarefa da TARDIS pedida pelo JARVIS em execução
 9. Executando uma tarefa      — EXECUTING, VERIFYING, RECOVERY
10. Pensando                   — THINKING, DECIDING, PLANNING, CONTEXT, PERCEIVING, IMAGINING
11. Inicializando              — BOOTING (progresso real dos componentes)
12. Aguardando interação       — nenhum dos anteriores

Cada estado tem o seu estilo (cor, brilho, olhos, movimento) — DESIGN_VISUAL.md §2.1.
"""
from __future__ import annotations

from dataclasses import dataclass

ERROR_WINDOW = 8.0
ALERT_WINDOW = 6.0
THINKING = frozenset({"THINKING", "DECIDING", "PLANNING", "CONTEXT", "PERCEIVING", "IMAGINING", "SIMULATING"})
EXECUTING = frozenset({"EXECUTING", "VERIFYING", "RECOVERY"})


@dataclass(frozen=True)
class StateStyle:
    key: str
    label: str
    rgb: tuple[int, int, int]            # cor principal do holograma
    iris: tuple[int, int, int]           # cor da íris
    glow: float                          # intensidade geral (0..1)
    eye_open: float                      # abertura dos olhos (1 = normal)
    brow: float                          # sobrancelhas: + erguidas, − franzidas
    head: float                          # amplitude do movimento sutil da cabeça
    scan: float                          # velocidade da linha de varredura
    rings: float                         # velocidade dos anéis de dados
    particles: float                     # densidade relativa de partículas
    priority: int


CYAN = (0, 217, 255)
GLOW = (103, 243, 255)
ELECTRIC = (22, 139, 255)
AMBER = (255, 179, 71)
CORAL = (255, 93, 115)
DIM = (61, 88, 115)

STYLES: dict[str, StateStyle] = {s.key: s for s in (
    StateStyle("privacidade", "PRIVACIDADE · MICROFONE DESLIGADO", DIM, DIM, 0.35, 0.0, 0.0, 0.25, 0.0, 0.1, 0.0, 1),
    StateStyle("erro", "ERRO DE INTEGRAÇÃO", CORAL, CORAL, 0.75, 0.9, -0.2, 0.5, 0.6, 0.3, 0.5, 2),
    StateStyle("confirmacao", "AGUARDANDO CONFIRMAÇÃO", AMBER, GLOW, 0.85, 1.1, 0.7, 0.4, 0.5, 0.4, 0.6, 3),
    StateStyle("falando", "FALANDO", CYAN, GLOW, 1.0, 1.0, 0.15, 0.8, 1.0, 1.0, 1.0, 4),
    StateStyle("alerta", "ALERTA", AMBER, AMBER, 1.0, 1.25, 0.8, 0.5, 1.4, 1.2, 0.9, 5),
    StateStyle("reconhecendo", "RECONHECENDO", GLOW, GLOW, 0.95, 1.05, 0.35, 0.3, 1.3, 1.5, 0.9, 6),
    StateStyle("escutando", "ESCUTANDO", CYAN, GLOW, 0.9, 1.15, 0.55, 0.5, 1.0, 0.8, 0.8, 7),
    StateStyle("tardis", "CONSULTANDO A TARDIS", CYAN, AMBER, 0.9, 0.95, 0.1, 0.6, 1.2, 1.6, 0.9, 8),
    StateStyle("executando", "EXECUTANDO", ELECTRIC, GLOW, 0.95, 0.95, -0.25, 0.35, 1.6, 2.0, 1.0, 9),
    StateStyle("pensando", "PENSANDO", ELECTRIC, GLOW, 0.85, 0.9, -0.35, 0.7, 1.1, 1.3, 0.8, 10),
    StateStyle("inicializando", "INICIALIZANDO", CYAN, GLOW, 0.8, 0.0, 0.0, 0.2, 2.0, 0.6, 0.5, 11),
    StateStyle("aguardando", "EM ESPERA", CYAN, GLOW, 0.7, 1.0, 0.0, 1.0, 0.6, 0.35, 0.5, 12),
)}
ORDER = tuple(sorted(STYLES, key=lambda k: STYLES[k].priority))
SHORT = {"privacidade": "PRIVACIDADE", "erro": "ERRO", "confirmacao": "CONFIRMAÇÃO", "falando": "FALANDO",
         "alerta": "ALERTA", "reconhecendo": "RECONHECENDO", "escutando": "ESCUTANDO", "tardis": "TARDIS",
         "executando": "EXECUTANDO", "pensando": "PENSANDO", "inicializando": "INICIALIZANDO",
         "aguardando": "EM ESPERA"}


@dataclass
class AvatarSignals:
    """Sinais REAIS lidos do núcleo (estado central, voz, eventos)."""

    now: float = 0.0
    runtime_state: str = "BOOTING"
    booted: bool = False
    boot_progress: float = 0.0           # 0..1 (componentes iniciados / total)
    privacy_shield: bool = False
    authorization: bool = False
    audible: bool = False                # fala saindo agora (posição real de reprodução)
    listening: bool = False
    recognizing: bool = False
    tardis: bool = False
    error_until: float = 0.0
    error_text: str = ""
    alert_until: float = 0.0
    alert_text: str = ""
    authorization_text: str = ""
    tardis_text: str = ""


@dataclass(frozen=True)
class Resolved:
    key: str
    style: StateStyle
    alert_tint: bool                     # alerta ativo sobre um estado de prioridade menor
    detail: str                          # motivo/indicador mostrado junto do rótulo

    @property
    def label(self) -> str:
        return self.style.label


def active_states(s: AvatarSignals) -> list[str]:
    """Todos os estados verdadeiros agora, em ordem de prioridade."""
    state = str(s.runtime_state or "")
    checks = {
        "privacidade": s.privacy_shield,
        "erro": state == "ERROR" or s.now < s.error_until,
        "confirmacao": s.authorization or state == "AWAITING_AUTHORIZATION",
        "falando": s.audible,
        "alerta": s.now < s.alert_until or state == "REMINDING",
        "reconhecendo": s.listening and s.recognizing,
        "escutando": s.listening or state == "LISTENING",
        "tardis": s.tardis,
        "executando": state in EXECUTING,
        "pensando": state in THINKING,
        "inicializando": not s.booted or state == "BOOTING",
        "aguardando": True,
    }
    return [key for key in ORDER if checks[key]]


def resolve(s: AvatarSignals) -> Resolved:
    states = active_states(s)
    key = states[0]
    tint = "alerta" in states and key != "alerta" and STYLES[key].priority > STYLES["alerta"].priority
    detail = {"erro": s.error_text, "alerta": s.alert_text, "confirmacao": s.authorization_text,
              "tardis": s.tardis_text,
              "inicializando": f"{int(round(s.boot_progress * 100))}% dos componentes"}.get(key, "")
    if tint and not detail:
        detail = s.alert_text
    return Resolved(key, STYLES[key], tint, detail or "")
