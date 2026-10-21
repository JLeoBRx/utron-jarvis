"""Permissões por categoria — a camada que o usuário controla em CONFIGURAÇÕES > PERMISSÕES.

Seis categorias, como pedidas para o JARVIS ULTIMATE:

* ``consultar`` — leitura: estado, listas, buscas, diagnósticos, descoberta na rede, visão sem clique;
* ``configurar`` — ajustes reversíveis do computador e do JARVIS: volume, brilho, rádio, microfone,
  preferências, automações, inventário da rede;
* ``executar_programas`` — abrir/fechar programas e janelas, navegador, teclado e mouse, projetos de
  desenvolvimento e comandos do sistema (bloquear, desligar);
* ``arquivos`` — criar, escrever, editar, mover e copiar arquivos; notas, memória pessoal e exportações;
* ``apagar_dados`` — exclusões, inclusive para a Lixeira: arquivos, memória, automações, registros;
* ``robo`` — comandos ao robô Noctário. A PARADA DE EMERGÊNCIA não pertence a nenhuma categoria:
  nunca é bloqueada nem espera confirmação.

Cada categoria tem um modo:

* ``permitir`` — a categoria não acrescenta restrição; vale a decisão por risco da AutonomyPolicy;
* ``confirmar`` — sempre pergunta, mesmo em ações de risco baixo (e sem autorização permanente);
* ``bloquear`` — recusa, dizendo qual categoria está bloqueada e onde mudar.

Pisos que a configuração não rebaixa: ``apagar_dados`` e ``robo`` nunca ficam abaixo de
``confirmar``. Movimento e parâmetros do robô também são categorias SENSÍVEIS (autorização específica a
cada vez). A política é lida das configurações a cada decisão: mudar na tela vale para o próximo pedido.

Esta camada só RESTRINGE: nunca transforma uma decisão "authorize" ou "refuse" em "execute" — exceto a
parada de emergência, que precisa funcionar em qualquer estado.
"""
from __future__ import annotations

from typing import Any, Callable

from ..config.settings import PERMISSION_CATEGORIES, PERMISSION_MODES
from ..skills.base import Risk, Skill
from .autonomy import AutonomyDecision

LABELS = {
    "consultar": "consultar",
    "configurar": "alterar configurações",
    "executar_programas": "executar programas e comandos do sistema",
    "arquivos": "modificar arquivos e dados pessoais",
    "apagar_dados": "apagar dados",
    "robo": "comandos ao robô Noctário",
}
MODE_LABELS = {"permitir": "permitir (decide pelo risco)", "confirmar": "confirmar sempre", "bloquear": "bloquear"}
DEFAULT_POLICY = {"consultar": "permitir", "configurar": "permitir", "executar_programas": "permitir",
                  "arquivos": "permitir", "apagar_dados": "confirmar", "robo": "confirmar"}
FLOORS = {"apagar_dados": "confirmar", "robo": "confirmar"}
_STRICTNESS = {mode: index for index, mode in enumerate(PERMISSION_MODES)}      # permitir < confirmar < bloquear

# Classificação explícita das skills embutidas. Skills novas podem declarar ``permission`` (ou
# ``permission_for``); as que não declaram caem nas regras de ``category_for``.
SKILL_CATEGORIES = {
    # configurar
    "audio.volume": "configurar", "system.brightness": "configurar", "system.radio": "configurar",
    "voice.select_mic": "configurar", "memory.set_preference": "configurar", "automation.create": "configurar",
    "automation.set_enabled": "configurar", "network.device_update": "configurar",
    "network.update_vendors": "configurar",
    # (autonomy.revoke só REDUZ permissões: tem risco NONE e fica em "consultar", para nunca ser bloqueada
    # junto com "alterar configurações")
    # executar programas e comandos do sistema
    "app.open": "executar_programas", "app.close": "executar_programas", "app.terminate": "executar_programas",
    "fs.open": "executar_programas", "web.open_url": "executar_programas", "web.search": "executar_programas",
    "audio.media": "executar_programas", "window.close": "executar_programas",
    "window.show_desktop": "executar_programas", "window.state": "executar_programas",
    "window.switch": "executar_programas", "input.click": "executar_programas",
    "input.move_mouse": "executar_programas", "input.press_key": "executar_programas",
    "input.scroll": "executar_programas", "input.type_text": "executar_programas",
    "vision.click_element": "executar_programas", "dev.create_venv": "executar_programas",
    "dev.install_dependency": "executar_programas", "dev.run_project": "executar_programas",
    "network.open_admin": "executar_programas", "system.lock": "executar_programas",
    "system.power": "executar_programas", "jarvis.shutdown": "executar_programas",
    # consultar (leitura com risco baixo; o resto da leitura é deduzido do risco NONE)
    "dev.check_dependencies": "consultar", "network.scan": "consultar", "network.ping": "consultar",
    "network.check_device": "consultar", "network.devices": "consultar", "network.diagnose": "consultar",
    # modificar arquivos e dados pessoais
    "fs.create_file": "arquivos", "fs.create_folder": "arquivos", "fs.write_text": "arquivos",
    "fs.edit_text": "arquivos", "fs.move": "arquivos", "fs.copy": "arquivos", "vision.screenshot": "arquivos",
    "memory.remember": "arquivos", "memory.session_note": "arquivos", "memory.backup": "arquivos",
    "network.export": "arquivos", "secondbrain.capture": "arquivos", "secondbrain.update": "arquivos",
    "secondbrain.relate": "arquivos", "secondbrain.complete": "arquivos", "secondbrain.archive": "arquivos",
    "secondbrain.restore": "arquivos", "secondbrain.snooze": "arquivos", "secondbrain.dismiss": "arquivos",
    "secondbrain.export": "arquivos",
    # apagar dados (inclusive para a Lixeira)
    "fs.delete": "apagar_dados", "memory.forget": "apagar_dados", "automation.delete": "apagar_dados",
    "secondbrain.delete": "apagar_dados", "secondbrain.empty_trash": "apagar_dados",
    "activity.clear": "apagar_dados",
}
_BY_SKILL_CATEGORY = {"filesystem": "arquivos", "second_brain": "arquivos", "memory": "arquivos",
                      "applications": "executar_programas", "windows": "executar_programas",
                      "automation": "executar_programas", "browser": "executar_programas",
                      "development": "executar_programas", "system": "configurar", "audio": "configurar",
                      "noctario": "robo", "robot": "robo"}


def category_for(skill: Skill, args: dict | None = None) -> str:
    """Categoria de permissão desta chamada ('' = parada de emergência, fora das categorias)."""
    if getattr(skill, "emergency", False):
        return ""
    declared = ""
    permission_for = getattr(skill, "permission_for", None)
    if callable(permission_for):
        declared = permission_for(dict(args or {})) or ""
    if declared in PERMISSION_CATEGORIES:
        return declared
    if skill.name in SKILL_CATEGORIES:
        return SKILL_CATEGORIES[skill.name]
    if skill.name.startswith("noctario."):
        return "robo"
    try:
        risk = skill.risk_for(dict(args or {}))
    except Exception:
        risk = skill.risk
    if risk is Risk.NONE:
        return "consultar"
    if getattr(skill, "sensitive", "") == "permanent_delete":
        return "apagar_dados"
    return _BY_SKILL_CATEGORY.get(getattr(skill, "category", ""), "executar_programas")


def parse_policy(entries: Any) -> dict[str, str]:
    """``("robo=bloquear", ...)`` das configurações → política completa (padrões + escolhas + pisos)."""
    policy = dict(DEFAULT_POLICY)
    for item in entries or ():
        category, _, mode = str(item).partition("=")
        category, mode = category.strip(), mode.strip()
        if category in PERMISSION_CATEGORIES and mode in PERMISSION_MODES:
            policy[category] = mode
    for category, floor in FLOORS.items():
        if _STRICTNESS[policy[category]] < _STRICTNESS[floor]:
            policy[category] = floor
    return policy


def policy_entries(policy: dict[str, str]) -> tuple[str, ...]:
    """Política → forma gravada nas configurações (só o que difere do padrão)."""
    clean = parse_policy(f"{k}={v}" for k, v in policy.items())
    return tuple(f"{k}={clean[k]}" for k in PERMISSION_CATEGORIES if clean[k] != DEFAULT_POLICY[k])


class PermissionPolicy:
    def __init__(self, settings_getter: Callable[[], Any]):
        self._settings = settings_getter

    def policy(self) -> dict[str, str]:
        return parse_policy(getattr(self._settings(), "permission_policy", ()))

    def mode(self, category: str) -> str:
        return self.policy().get(category, "permitir")

    def describe(self) -> list[dict]:
        """Para a tela de configurações e para "quais são minhas permissões?"."""
        policy = self.policy()
        return [{"category": c, "label": LABELS[c], "mode": policy[c], "mode_label": MODE_LABELS[policy[c]],
                 "default": DEFAULT_POLICY[c], "floor": FLOORS.get(c, "permitir")} for c in PERMISSION_CATEGORIES]

    def apply(self, decision: AutonomyDecision, skill: Skill, args: dict | None = None) -> AutonomyDecision:
        """Restringe a decisão da AutonomyPolicy conforme a categoria da chamada."""
        if getattr(skill, "emergency", False):
            return AutonomyDecision("execute", "parada de emergência: nunca espera confirmação", decision.risk)
        category = category_for(skill, args)
        mode = self.mode(category)
        label = LABELS.get(category, category)
        if mode == "bloquear":
            return AutonomyDecision("refuse", f"a categoria \"{label}\" está bloqueada "
                                              "(CONFIGURAÇÕES > PERMISSÕES)", decision.risk, permission=category)
        if mode == "confirmar" and decision.action == "execute":
            return AutonomyDecision("authorize", f"a categoria \"{label}\" exige confirmação", decision.risk,
                                    permission=category)
        if mode == "confirmar" and decision.action == "authorize":
            decision.permission = category          # sem "sim, sempre" nesta categoria
        return decision
