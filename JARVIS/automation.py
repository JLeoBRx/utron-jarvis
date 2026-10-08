"""
J.A.R.V.I.S. // automações persistentes (allowlist, execução autorizada).
"""
import json
import re

import commands
import config
import memory

SAFE_AUTOMATION_ARGUMENTS = config.SAFE_AUTOMATION_ARGUMENTS


def _bounded_text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Texto ausente ou acima do limite permitido.")
    return value.strip()


def normalize_trigger(value):
    cleaned = " ".join(re.sub(r"[^\w\s]", " ", commands.norm(value)).split())
    return cleaned


def _validate_automation(tool_name, arguments):
    if tool_name not in SAFE_AUTOMATION_ARGUMENTS or type(arguments) is not dict:
        raise ValueError("Ação de automação não permitida.")
    allowed = SAFE_AUTOMATION_ARGUMENTS[tool_name]
    if set(arguments) - allowed:
        raise ValueError("A automação contém argumentos não permitidos.")
    required = {
        "open_app": {"name"}, "search_web": {"query"}, "open_url": {"url"},
        "control_volume": {"direction"}, "control_media": {"action"},
        "take_screenshot": set(), "search_files": {"name"},
    }[tool_name]
    if required - set(arguments):
        raise ValueError("Faltam argumentos obrigatórios para a automação.")
    if tool_name == "open_app" and commands.norm(arguments["name"]) not in commands.APPS:
        raise ValueError("Aplicativo não configurado.")
    if tool_name == "open_url":
        arguments["url"] = commands._validate_url(_bounded_text(arguments["url"], 1500))
    if tool_name == "search_web":
        _bounded_text(arguments["query"], 300)
        if arguments.get("site", "google") not in ("google", "youtube"):
            raise ValueError("Site de busca não permitido.")
    if tool_name == "control_volume" and arguments["direction"] not in ("up", "down", "mute"):
        raise ValueError("Ação de volume não permitida.")
    if tool_name == "control_media" and arguments["action"] not in ("play_pause", "next", "previous"):
        raise ValueError("Ação de mídia não permitida.")
    if tool_name == "search_files":
        _bounded_text(arguments["name"], 200)
        if arguments.get("root"):
            _bounded_text(arguments["root"], 1000)
    return arguments


def create_automation(name, trigger, tool_name, arguments):
    name = _bounded_text(name, 60)
    trigger = _bounded_text(trigger, 100)
    normalized = normalize_trigger(trigger)
    if not normalized:
        raise ValueError("A frase de ativação está vazia.")
    validated = _validate_automation(tool_name, dict(arguments))
    with memory.open_db() as connection:
        connection.execute(
            "INSERT INTO automations(name,trigger_text,tool_name,arguments,enabled) VALUES(?,?,?,?,1) "
            "ON CONFLICT(name) DO UPDATE SET trigger_text=excluded.trigger_text, "
            "tool_name=excluded.tool_name, arguments=excluded.arguments, enabled=1",
            (name, normalized, tool_name, json.dumps(validated, ensure_ascii=False)),
        )
    return f"Automação {name} salva para a frase exata: {trigger}."


def list_automations():
    with memory.open_db() as connection:
        rows = connection.execute(
            "SELECT name,trigger_text,tool_name,enabled FROM automations ORDER BY name LIMIT 30"
        ).fetchall()
    if not rows:
        return "Nenhuma automação está configurada."
    parts = []
    for name, trigger, tool, enabled in rows:
        state = "ativa" if enabled else "pausada"
        parts.append(f"{name} ({state}): {trigger} → {tool}")
    return "Automações: " + "; ".join(parts)


def automation_status():
    with memory.open_db() as connection:
        row = connection.execute(
            "SELECT COUNT(*), SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) FROM automations"
        ).fetchone()
    total = int(row[0] or 0)
    enabled = int(row[1] or 0)
    if total == 0:
        return None, "NENHUMA"
    return True, f"{enabled}/{total} ATIVAS"


def set_enabled(name, enabled):
    name = _bounded_text(name, 60)
    with memory.open_db() as connection:
        cursor = connection.execute(
            "UPDATE automations SET enabled=? WHERE lower(name)=lower(?)",
            (1 if enabled else 0, name),
        )
    if not cursor.rowcount:
        return "Não encontrei essa automação."
    return f"Automação {name} {'ativada' if enabled else 'pausada'}."


def delete_automation(name):
    name = _bounded_text(name, 60)
    with memory.open_db() as connection:
        cursor = connection.execute("DELETE FROM automations WHERE lower(name)=lower(?)", (name,))
    return "Automação removida." if cursor.rowcount else "Não encontrei essa automação."


def run_matching(text, on_execute=None, on_error=None):
    normalized = normalize_trigger(text)
    if not normalized:
        return False, None
    with memory.open_db() as connection:
        row = connection.execute(
            "SELECT name,tool_name,arguments FROM automations "
            "WHERE enabled=1 AND trigger_text=? LIMIT 1",
            (normalized,),
        ).fetchone()
    if row is None:
        return False, None

    name, tool_name, raw_arguments = row
    arguments = json.loads(raw_arguments)
    handled, response = commands.execute_tool(
        tool_name,
        arguments,
        on_execute=on_execute,
        on_error=on_error,
    )
    if not handled:
        return True, f"A automação {name} foi bloqueada por uma ferramenta não permitida."
    if not commands.is_confirmation_pending():
        verification = commands.verify_tool(tool_name, arguments, response)
        memory.audit("automation", tool_name, f"{name}: {response}", verification.get("verified"))
        if not verification["verified"]:
            return True, f"A automação {name} terminou sem verificação: {verification['evidence']}"
    else:
        memory.audit("automation", tool_name, f"{name}: aguardando confirmação", False)
    return True, response
