"""J.A.R.V.I.S. // CAPABILITY MODEL
Mapa declarativo de capacidades: descreve o que cada ferramenta consegue produzir.
Não executa ferramentas nem concede permissões.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    tools: tuple[str, ...]
    risk: str = "low"
    evidence: tuple[str, ...] = ()

    def to_dict(self):
        return asdict(self)

_CAPABILITIES = (
    Capability("read_screen", "ler texto e conteúdo visível", ("ocr_screen", "inspect_screen", "take_screenshot"), evidence=("ocr", "visual")),
    Capability("understand_ui", "entender controles e elementos da interface", ("list_ui_elements", "locate_on_screen", "inspect_screen"), evidence=("ui", "foreground")),
    Capability("interact_ui", "interagir com um elemento descrito", ("click_by_description",), "medium", ("ui", "foreground")),
    Capability("launch_application", "abrir aplicativo", ("open_app",), "medium"),
    Capability("navigate_web", "abrir e pesquisar páginas na web", ("open_url", "search_web"), "medium"),
    Capability("find_files", "localizar arquivos e documentos", ("search_files",)),
    Capability("inspect_system", "consultar estado do sistema", ("system_status",)),
    Capability("control_media", "controlar volume ou reprodução", ("control_volume", "control_media"), "medium"),
    Capability("wait_for_state", "aguardar estabilização ou carregamento", ("wait_seconds",)),
    Capability("remember_information", "guardar informação autorizada", ("remember_fact",), "medium"),
    Capability("recall_information", "recuperar informação previamente guardada", ("recall_facts",)),
)

_BY_NAME = {c.name: c for c in _CAPABILITIES}
_TOOL_TO_CAPS = {}
for _cap in _CAPABILITIES:
    for _tool in _cap.tools:
        _TOOL_TO_CAPS.setdefault(_tool, []).append(_cap.name)


def all_capabilities():
    return [c.to_dict() for c in _CAPABILITIES]


def for_tool(tool_name: str):
    return list(_TOOL_TO_CAPS.get(str(tool_name), ()))


def infer(goal: str, context: dict | None = None, limit: int = 5):
    """Infere capacidades necessárias sem executar nem expor raciocínio interno."""
    text = str(goal or "").lower()
    context = context or {}
    rules = {
        "read_screen": ("texto", "ler", "tela", "erro", "mensagem", "escrito", "captura", "print"),
        "understand_ui": ("botão", "menu", "campo", "janela", "interface", "ícone", "controle"),
        "interact_ui": ("clique", "clicar", "pressione", "selecionar", "fechar", "abrir"),
        "launch_application": ("abrir aplicativo", "inicie", "aplicativo"),
        "navigate_web": ("site", "url", "página", "internet", "web", "pesquise"),
        "find_files": ("arquivo", "pasta", "documento"),
        "inspect_system": ("bateria", "wifi", "bluetooth", "brilho", "sistema"),
        "control_media": ("volume", "som", "música", "play", "pause", "mudo"),
        "wait_for_state": ("aguarde", "espere", "carregamento", "carregar"),
        "remember_information": ("lembre", "memorize", "guardar"),
        "recall_information": ("lembra", "memória", "recorde"),
    }
    scored = []
    for cap in _CAPABILITIES:
        score = 0.0
        hits = [h for h in rules.get(cap.name, ()) if h in text]
        score += min(0.8, 0.2 * len(hits))
        if context.get("visual") or context.get("screen") or context.get("ocr"):
            if cap.name in {"read_screen", "understand_ui", "interact_ui"}:
                score += 0.15
        if context.get("foreground") and cap.name in {"understand_ui", "interact_ui"}:
            score += 0.05
        if score > 0:
            scored.append((cap, min(score, 1.0), hits))
    scored.sort(key=lambda x: (-x[1], x[0].name))
    return [{**c.to_dict(), "score": score, "signals": hits} for c, score, hits in scored[:max(1, int(limit))]]


def tools_for(capability_names):
    tools = []
    for name in capability_names:
        cap = _BY_NAME.get(str(name))
        if cap:
            for tool in cap.tools:
                if tool not in tools:
                    tools.append(tool)
    return tools
