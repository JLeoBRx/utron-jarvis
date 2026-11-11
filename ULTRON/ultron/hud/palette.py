"""Paleta do SAFRA sem Qt — a fonte única de cores, tons e intensidades por estado.

Os valores vêm de ``ultron/hud/design/tokens.json`` (o teste ``DesignTokensTest`` confere). ``theme.py``
constrói as cores e as folhas de estilo do Qt a partir daqui; as cenas 2D (``scene.py``,
``tardis_scene.py``) usam os mesmos valores sem depender de Qt (testáveis).

Semântica: o VERMELHO SAFRA é atividade, escuta e dados em movimento; o BORDÔ é repouso e profundidade; o
vermelho-framboesa ("energy") marca pensamento, planejamento e execução; o brilho claro é fala e
confirmação. Âmbar é atenção/autorização pendente e laranja é falha real — fora da família do vermelho
para nunca se confundirem com a identidade. Violeta e cromo pertencem só ao Protocolo ULTRON.
"""
from __future__ import annotations

NAME = "safra-red"
HEX = {
    "space": "#07070A", "abyss": "#0F1013", "deep": "#17181C", "graphite": "#23252B", "muted": "#5C1A24",
    "wine": "#7A0F1F", "primary": "#EA2840", "glow": "#FF5C6C", "energy": "#FF3B6B", "text": "#F4F4F5",
    "dim_text": "#A1A1AA", "alert": "#F7C948", "error": "#FF7B1C",
}
# cores do Protocolo ULTRON (identidade alternativa): só ele usa
ULTRON_HEX = {"ultron": "#8B5CF6", "ultron_glow": "#B794FF", "ultron_deep": "#1C0F33", "ultron_metal": "#A9B0BC"}
# tons de partículas/pulsos/nós → cor (os nomes dos tons são identificadores internos das cenas)
TONE_HEX = {"cyan": HEX["primary"], "primary": HEX["primary"], "glow": HEX["glow"], "blue": HEX["energy"],
            "electric": HEX["energy"], "energy": HEX["energy"], "ice": HEX["text"], "dim": HEX["muted"],
            "deep": HEX["wine"], "alert": HEX["alert"], "error": HEX["error"], "gold": HEX["primary"],
            "amber": HEX["alert"], "white": HEX["text"]}
# estado de atividade (contrato do núcleo) → (cor, intensidade do halo 0..1, efeito)
STATE = {
    "IDLE": (HEX["wine"], 0.25, "bordô discreto"),
    "LISTENING": (HEX["primary"], 0.75, "halo vermelho suave"),
    "PERCEIVING": (HEX["primary"], 0.6, "ondas sutis"),
    "CONTEXT": (HEX["energy"], 0.55, "memória consultada"),
    "DECIDING": (HEX["energy"], 0.6, "conexões se acendem"),
    "PLANNING": (HEX["energy"], 0.7, "conexões progressivamente iluminadas"),
    "EXECUTING": (HEX["primary"], 0.85, "pulsos acompanham a operação"),
    "VERIFYING": (HEX["glow"], 0.7, "confirmação"),
    "RECOVERY": (HEX["alert"], 0.6, "correção em andamento"),
    "SPEAKING": (HEX["glow"], 0.8, "sincronizado com a voz"),
    "REMINDING": (HEX["glow"], 0.8, "lembrete"),
    "IMAGINING": (HEX["energy"], 0.65, "espaço interno com profundidade"),
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


def rgb(key: str) -> str:
    """"r, g, b" de uma cor da paleta (para folhas de estilo com transparência)."""
    value = {**HEX, **ULTRON_HEX}[key].lstrip("#")
    return ", ".join(str(int(value[i:i + 2], 16)) for i in (0, 2, 4))


def contrast(fg: str, bg: str) -> float:
    """Razão de contraste WCAG 2.1 entre duas cores #RRGGBB."""
    def lum(h: str) -> float:
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)
