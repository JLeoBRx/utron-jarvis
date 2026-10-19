"""Paleta do JARVIS sem Qt — a fonte única de cores, tons e intensidades por estado.

``theme.py`` constrói as cores do Qt a partir daqui; as cenas (``scene.py``,
``tardis_scene.py``) usam os mesmos valores sem depender de Qt (testáveis).
"""
from __future__ import annotations

NAME = "jarvis-blue"
HEX = {
    "space": "#030712", "abyss": "#071426", "deep": "#0B1F3A", "tech": "#075985", "cyan": "#00D9FF",
    "glow": "#67F3FF", "electric": "#168BFF", "ice": "#DCEEFF", "dim_text": "#7F9BB7", "alert": "#FFB547",
    "error": "#FF5D73",
}
# tons de partículas/pulsos/nós → cor
TONE_HEX = {"cyan": HEX["cyan"], "glow": HEX["glow"], "blue": HEX["electric"], "electric": HEX["electric"],
            "ice": HEX["ice"], "dim": HEX["tech"], "deep": HEX["tech"], "alert": HEX["alert"], "error": HEX["error"],
            "gold": HEX["cyan"], "amber": HEX["alert"], "white": HEX["ice"]}
# estado de atividade (contrato do núcleo) → (cor, intensidade do halo 0..1, efeito)
STATE = {
    "IDLE": (HEX["deep"], 0.25, "azul profundo discreto"),
    "LISTENING": (HEX["cyan"], 0.75, "halo ciano suave"),
    "PERCEIVING": (HEX["cyan"], 0.6, "ondas sutis"),
    "CONTEXT": (HEX["electric"], 0.55, "memória consultada"),
    "DECIDING": (HEX["electric"], 0.6, "conexões se acendem"),
    "PLANNING": (HEX["electric"], 0.7, "conexões progressivamente iluminadas"),
    "EXECUTING": (HEX["cyan"], 0.85, "pulsos acompanham a operação"),
    "VERIFYING": (HEX["glow"], 0.7, "confirmação"),
    "RECOVERY": (HEX["alert"], 0.6, "correção em andamento"),
    "SPEAKING": (HEX["glow"], 0.8, "sincronizado com a voz"),
    "REMINDING": (HEX["glow"], 0.8, "lembrete"),
    "IMAGINING": (HEX["electric"], 0.65, "espaço interno com profundidade"),
    "ERROR": (HEX["error"], 0.6, "falha identificável"),
}
# rótulo exibido para cada estado
STATE_LABEL = {"IDLE": "REPOUSO", "LISTENING": "ESCUTANDO", "PERCEIVING": "PERCEBENDO", "CONTEXT": "CONTEXTO",
               "DECIDING": "DECIDINDO", "PLANNING": "PLANEJANDO", "EXECUTING": "EXECUTANDO",
               "VERIFYING": "VERIFICANDO", "RECOVERY": "RECUPERANDO", "SPEAKING": "FALANDO",
               "REMINDING": "LEMBRETE", "IMAGINING": "IMAGINANDO", "ERROR": "ERRO"}


def state_glow(activity: str) -> float:
    return STATE.get(str(activity or "IDLE"), STATE["IDLE"])[1]


def state_label(activity: str) -> str:
    return STATE_LABEL.get(str(activity or "IDLE"), str(activity or ""))
