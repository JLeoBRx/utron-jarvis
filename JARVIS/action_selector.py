"""J.A.R.V.I.S. // ACTION SELECTION / TOOL INTELLIGENCE
Escolhe ferramentas candidatas para um objetivo antes da execução.
A seleção é apenas uma recomendação: a allowlist continua sendo a autoridade final.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

import config
import capability_model
import capability_discovery
import capability_graph

@dataclass
class ToolCandidate:
    name: str
    score: float
    reason: str
    risk: str = "low"

    def to_dict(self):
        return asdict(self)


_HINTS = {
    "ocr_screen": ("texto", "ler", "tela", "mensagem", "erro", "escrito", "código"),
    "list_ui_elements": ("botão", "controle", "janela", "interface", "menu", "campo"),
    "locate_on_screen": ("localize", "encontre", "onde está", "botão", "ícone", "campo"),
    "click_by_description": ("clique", "clicar", "pressione", "abrir", "selecionar"),
    "inspect_screen": ("analise a tela", "veja a tela", "observe", "visual", "imagem"),
    "open_app": ("abrir", "inicie", "execute aplicativo", "aplicativo"),
    "open_url": ("site", "url", "página", "acesse", "navegador"),
    "search_web": ("pesquise", "pesquisa", "web", "internet", "procure"),
    "search_files": ("arquivo", "pasta", "documento", "encontre o arquivo"),
    "take_screenshot": ("captura", "print", "screenshot"),
    "system_status": ("bateria", "wifi", "wi-fi", "bluetooth", "brilho", "sistema"),
    "wait_seconds": ("aguarde", "espere", "carregamento", "carregar"),
    "control_volume": ("volume", "som", "mudo"),
    "control_media": ("música", "media", "play", "pause", "próxima"),
    "remember_fact": ("lembre", "memorize", "guardar"),
    "recall_facts": ("lembra", "memória", "recorde"),
}


def _definitions_by_name():
    import tools
    return {d["function"]["name"]: d for d in tools.DEFINITIONS}


def select(goal: str, context: dict | None = None, limit: int = 5):
    text = str(goal or "").lower()
    context = context or {}
    inferred = capability_model.infer(goal, context, limit=8)
    capability_scores = {}
    capability_reasons = {}
    graph_candidates = {x["tool"] for x in capability_graph.tools_for([x["name"] for x in inferred], max_tools=32)}
    for item in inferred:
        capability_scores[item["name"]] = float(item.get("score", 0.0))
        capability_reasons[item["name"]] = item.get("signals", [])
    candidates = []
    defs = _definitions_by_name()
    for name in defs:
        score = 0.05
        reasons = []
        if name in graph_candidates:
            score += 0.08
            reasons.append("grafo de capacidades")
        for capability in capability_model.for_tool(name):
            cap_score = capability_scores.get(capability, 0.0)
            if cap_score:
                score += 0.22 * cap_score
                reasons.append("capacidade:" + capability)
        hints = _HINTS.get(name, ())
        for hint in hints:
            if hint in text:
                score += 0.18
                reasons.append(hint)
        if context.get("visual") or context.get("screen") or context.get("ocr"):
            if name in {"ocr_screen", "inspect_screen", "list_ui_elements", "locate_on_screen"}:
                score += 0.16
                reasons.append("contexto visual")
        if context.get("foreground") and name in {"list_ui_elements", "locate_on_screen", "ocr_screen"}:
            score += 0.08
            reasons.append("janela em primeiro plano")
        risk = "medium" if name in {"click_by_description", "delete_automation", "forget_fact"} else "low"
        if name == "click_by_description":
            score -= 0.03  # ação física só sobe quando há intenção explícita de clique
        if score > 0.05:
            candidates.append(ToolCandidate(name, min(score, 1.0), ", ".join(reasons) or "ferramenta registrada", risk))
    candidates.sort(key=lambda x: (-x.score, x.name))
    return candidates[:max(1, int(limit))]


def guidance(goal: str, context: dict | None = None, limit: int = 5) -> str:
    selected = select(goal, context, limit)
    capabilities = capability_model.infer(goal, context, limit=4)
    discovered = capability_discovery.catalog()
    if not selected:
        return "Nenhuma ferramenta recebeu prioridade específica."
    parts = [f"{c.name} ({c.score:.2f}: {c.reason})" for c in selected]
    cap_names = ", ".join(x["name"] for x in capabilities) or "nenhuma específica"
    discovered_count = len(discovered)
    return "Capacidades prioritárias: " + cap_names + ". Catálogo descoberto: " + str(discovered_count) + " ferramentas. Ferramentas candidatas para este passo: " + "; ".join(parts) + ". A seleção final deve respeitar a allowlist e a evidência disponível."
