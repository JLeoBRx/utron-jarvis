"""J.A.R.V.I.S. // CAPABILITY DISCOVERY
Descobre as ferramentas realmente registradas e constrói um catálogo de capacidades.
Discovery descreve capacidades; não concede permissão nem executa ferramentas.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
import capability_model

@dataclass(frozen=True)
class ToolCapability:
    tool: str
    description: str
    capabilities: tuple[str, ...]
    risk: str = "low"
    evidence: tuple[str, ...] = ()
    available: bool = True

    def to_dict(self):
        return asdict(self)


def _tool_definitions():
    import tools
    return list(tools.DEFINITIONS)


def _risk(tool: str) -> str:
    if tool in {"click_by_description", "delete_automation", "forget_fact"}:
        return "medium"
    return "low"


def _keywords(name: str, description: str) -> set[str]:
    text = (name + " " + description).lower()
    return set(re.findall(r"[a-záàâãéêíóôõúç_-]+", text))


def _discover_capabilities(tool: str, description: str):
    known = list(capability_model.for_tool(tool))
    words = _keywords(tool, description)
    # Fallback semântico para ferramentas novas que ainda não estejam no mapa manual.
    heuristics = {
        "read_screen": {"ocr", "tela", "screen", "texto", "screenshot", "captura"},
        "understand_ui": {"interface", "ui", "controle", "elementos", "janela"},
        "interact_ui": {"clicar", "clique", "interagir"},
        "launch_application": {"abrir", "aplicativo", "application"},
        "navigate_web": {"web", "url", "página", "pesquisar", "internet"},
        "find_files": {"arquivo", "arquivos", "pasta", "documento"},
        "inspect_system": {"sistema", "bateria", "wifi", "bluetooth", "brilho"},
        "control_media": {"volume", "música", "media", "play", "pause"},
        "wait_for_state": {"aguardar", "aguarde", "esperar", "carregamento"},
        "remember_information": {"guardar", "memória", "lembrar", "memorizar"},
        "recall_information": {"consultar", "recuperar", "memória", "lembrar"},
    }
    for capability, hints in heuristics.items():
        if words & hints and capability not in known:
            known.append(capability)
    return tuple(known)


def discover():
    result = []
    for item in _tool_definitions():
        function = item.get("function", {})
        name = str(function.get("name", "")).strip()
        if not name:
            continue
        description = str(function.get("description", "")).strip()
        caps = _discover_capabilities(name, description)
        evidence = []
        for cap in caps:
            definition = next((x for x in capability_model.all_capabilities() if x["name"] == cap), None)
            if definition:
                for ev in definition.get("evidence", ()):
                    if ev not in evidence:
                        evidence.append(ev)
        result.append(ToolCapability(name, description, caps, _risk(name), tuple(evidence)).to_dict())
    return result


def catalog():
    return discover()


def by_tool(tool_name: str):
    name = str(tool_name)
    return next((x for x in discover() if x["tool"] == name), None)


def tools_for_capability(capability: str):
    cap = str(capability)
    return [x for x in discover() if cap in x["capabilities"]]


def validate():
    catalog_items = discover()
    names = {x["tool"] for x in catalog_items}
    registered = {item["function"]["name"] for item in _tool_definitions()}
    orphaned = sorted(names - registered)
    uncovered = sorted(registered - names)
    return {
        "tool_count": len(catalog_items),
        "capability_links": sum(len(x["capabilities"]) for x in catalog_items),
        "orphaned": orphaned,
        "uncovered": uncovered,
        "ok": not orphaned and not uncovered,
    }
