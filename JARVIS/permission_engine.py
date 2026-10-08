"""J.A.R.V.I.S. // motor central de permissões e autonomia.

Decide se uma ferramenta pode ser executada automaticamente, exige confirmação
ou deve ser bloqueada. A política é persistida localmente e não libera shell.
"""
import json
import os
import threading

import config

LOCK = threading.RLock()
MODES = ("supervised", "autonomous", "locked")
MODE_LABELS = {
    "supervised": "AUTÔNOMO SUPERVISIONADO",
    "autonomous": "AUTÔNOMO",
    "locked": "BLOQUEADO",
}
DEFAULT_MODE = "supervised"

# Risco padrão das ferramentas. O motor ainda respeita confirmações internas
# existentes em commands.py.
LOW = "low"
MEDIUM = "medium"
HIGH = "high"

RISK = {
    "get_context": LOW, "ocr_screen": LOW, "list_ui_elements": LOW,
    "locate_on_screen": LOW, "verify_ui_action": LOW,
    "system_status": LOW, "take_screenshot": LOW, "inspect_screen": LOW,
    "wait_seconds": LOW, "search_files": LOW, "recall_facts": LOW,
    "get_profile": LOW, "read_audit": LOW, "list_automations": LOW,
    "open_app": LOW, "open_url": LOW, "search_web": LOW,
    "control_volume": LOW, "control_media": LOW, "control_brightness": LOW,
    "scroll": LOW, "move_mouse": LOW, "press_key": MEDIUM,
    "type_text": MEDIUM, "mouse_click": MEDIUM, "click_by_description": MEDIUM,
    "execute_ui_action": MEDIUM, "control_window": MEDIUM,
    "open_path": MEDIUM, "create_folder": MEDIUM, "copy_path": MEDIUM,
    "set_preference": MEDIUM, "add_session_note": LOW,
    "create_automation": MEDIUM, "set_automation_enabled": MEDIUM,
    "remember_fact": LOW, "set_personality": LOW,
    "close_app": HIGH, "move_path": HIGH, "delete_path": HIGH,
    "forget_fact": HIGH, "delete_automation": HIGH, "control_radio": HIGH,
    "power": HIGH,
}

# Ferramentas que nunca devem ser liberadas por um modo genérico.
NEVER_AUTO = frozenset({
    "close_app", "move_path", "delete_path", "forget_fact",
    "delete_automation", "control_radio", "power",
})


class PermissionEngine:
    def __init__(self, path=None):
        self.path = path or os.path.join(config.data_dir(), "permissions.json")
        self.mode = DEFAULT_MODE
        self.overrides = {}
        self._load()

    def _load(self):
        with LOCK:
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("mode") in MODES:
                    self.mode = data["mode"]
                self.overrides = {
                    str(k): str(v) for k, v in (data.get("overrides") or {}).items()
                    if str(v) in {"allow", "confirm", "deny"}
                }
            except (OSError, ValueError, TypeError):
                self.mode = DEFAULT_MODE
                self.overrides = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"mode": self.mode, "overrides": self.overrides}, fh,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def risk(self, tool_name):
        return RISK.get(tool_name, HIGH)

    def decision(self, tool_name):
        if tool_name in config.FORBIDDEN_TOOL_NAMES:
            return "deny"
        override = self.overrides.get(tool_name)
        if override:
            return override
        if tool_name in NEVER_AUTO:
            return "confirm"
        risk = self.risk(tool_name)
        if self.mode == "locked":
            return "deny" if risk != LOW else "allow"
        if self.mode == "supervised":
            return {LOW: "allow", MEDIUM: "confirm", HIGH: "confirm"}[risk]
        # autonomous: baixo e médio podem operar; alto continua confirmado.
        return {LOW: "allow", MEDIUM: "allow", HIGH: "confirm"}[risk]

    def set_mode(self, mode):
        mode = str(mode).strip().lower()
        if mode not in MODES:
            raise ValueError("Modo de permissão inválido.")
        with LOCK:
            self.mode = mode
            self._save()
        return MODE_LABELS[mode]

    def set_override(self, tool_name, decision):
        if decision not in {"allow", "confirm", "deny"}:
            raise ValueError("Decisão inválida.")
        with LOCK:
            self.overrides[str(tool_name)] = decision
            self._save()

    def clear_override(self, tool_name):
        with LOCK:
            self.overrides.pop(str(tool_name), None)
            self._save()

    def summary(self):
        return {
            "mode": self.mode,
            "label": MODE_LABELS[self.mode],
            "overrides": dict(self.overrides),
            "never_auto": sorted(NEVER_AUTO),
        }


_ENGINE = PermissionEngine()


def engine():
    return _ENGINE


def decide(tool_name):
    return _ENGINE.decision(tool_name)


def risk(tool_name):
    return _ENGINE.risk(tool_name)


def summary():
    return _ENGINE.summary()


def set_mode(mode):
    return _ENGINE.set_mode(mode)


def set_override(tool_name, decision):
    _ENGINE.set_override(tool_name, decision)
    return f"Permissão de {tool_name}: {decision}."


def clear_override(tool_name):
    _ENGINE.clear_override(tool_name)
    return f"Permissão específica removida para {tool_name}."
