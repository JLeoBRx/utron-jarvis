"""
J.A.R.V.I.S. // registro de ferramentas allowlisted.

A IA só pode chamar nomes deste registro. Shell/CMD/Python livres não existem aqui.
"""
import commands
import config
import memory
import automation
import vision

_vision_chat = None


def configure(vision_chat=None):
    global _vision_chat
    _vision_chat = vision_chat


def _tool(name, description, properties=None, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


EXTRA_DEFINITIONS = [
    _tool("remember_fact", "Guardar localmente um fato pessoal pedido pelo usuário.",
          {"subject": {"type": "string", "maxLength": 80},
           "fact": {"type": "string", "maxLength": 500}}, ("subject", "fact")),
    _tool("recall_facts", "Consultar fatos salvos localmente.",
          {"query": {"type": "string", "maxLength": 120}}, ("query",)),
    _tool("forget_fact", "Esquecer um fato local; exige confirmação falada.",
          {"subject": {"type": "string", "maxLength": 80}}, ("subject",)),
    _tool("set_personality", "Consultar/selecionar o estilo de resposta; nesta instalação a personalidade JARVIS é fixa.",
          {"style": {"type": "string", "enum": sorted(config.PERSONALITIES)}}, ("style",)),
    _tool("get_profile", "Ler perfil e preferências locais (sem credenciais)."),
    _tool("set_preference", "Atualizar uma preferência local permitida.",
          {"name": {"type": "string", "enum": ["profile_name", "city", "language", "address_me_as"]},
           "value": {"type": "string", "maxLength": 200}}, ("name", "value")),
    _tool("add_session_note", "Anotar contexto temporário desta sessão.",
          {"note": {"type": "string", "maxLength": 300}}, ("note",)),
    _tool("read_audit", "Ler os últimos eventos da auditoria local.",
          {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}),
    _tool("create_automation", "Criar automação por frase exata; ferramenta restrita à allowlist não destrutiva.",
          {"name": {"type": "string", "maxLength": 60},
           "trigger": {"type": "string", "maxLength": 100},
           "tool_name": {"type": "string", "enum": sorted(config.SAFE_AUTOMATION_ARGUMENTS)},
           "arguments": {"type": "object"}},
          ("name", "trigger", "tool_name", "arguments")),
    _tool("list_automations", "Listar automações locais configuradas."),
    _tool("set_automation_enabled", "Pausar ou reativar uma automação pelo nome.",
          {"name": {"type": "string", "maxLength": 60},
           "enabled": {"type": "boolean"}}, ("name", "enabled")),
    _tool("delete_automation", "Remover uma automação local; exige confirmação falada.",
          {"name": {"type": "string", "maxLength": 60}}, ("name",)),
    _tool("ocr_screen", "Ler texto visível na tela via OCR, se o motor estiver instalado."),
    _tool("list_ui_elements", "Listar controles acessíveis da janela em primeiro plano, se UI Automation existir."),
    _tool("locate_on_screen", "Localizar elementos por nome/texto via OCR e acessibilidade.",
          {"description": {"type": "string", "maxLength": 200}}, ("description",)),
    _tool("click_by_description", "Clicar em um elemento único encontrado por descrição; exige confirmação.",
          {"description": {"type": "string", "maxLength": 200}}, ("description",)),
]

DEFINITIONS = list(commands.TOOL_DEFINITIONS) + EXTRA_DEFINITIONS
NAMES = {item["function"]["name"] for item in DEFINITIONS}
_EXTRA_NAMES = {item["function"]["name"] for item in EXTRA_DEFINITIONS}


def is_forbidden(name):
    return name in config.FORBIDDEN_TOOL_NAMES or name not in NAMES


def _args(arguments, required, optional=()):
    if type(arguments) is not dict:
        raise ValueError("Os argumentos da ferramenta devem ser um objeto.")
    allowed = set(required) | set(optional)
    if set(arguments) - allowed or set(required) - set(arguments):
        raise ValueError("Os argumentos não correspondem ao esquema permitido.")
    return arguments


def execute(name, arguments, on_execute=None, on_error=None):
    if name in config.FORBIDDEN_TOOL_NAMES:
        return False, "A ferramenta solicitada não está permitida.", {"verified": False, "evidence": "allowlist"}
    if name not in NAMES:
        return False, "A ferramenta solicitada não está permitida.", {"verified": False, "evidence": "fora da allowlist"}

    if name not in _EXTRA_NAMES:
        if name == "inspect_screen":
            try:
                args = _args(arguments, ("question",))
                on_execute and on_execute()
                handled, result, verification = vision.inspect_with_model(args["question"], _vision_chat)
                return handled, result, verification
            except Exception as exc:
                on_error and on_error()
                result = f"Ferramenta recusada ou inválida: {exc}"
                return True, result, {"verified": False, "evidence": result}
        handled, result = commands.execute_tool(name, arguments, on_execute=on_execute, on_error=on_error)
        if not handled:
            return False, result, {"verified": False, "evidence": "Ferramenta fora da allowlist."}
        if commands.is_confirmation_pending():
            return True, result, {"verified": False, "evidence": result or "Aguardando confirmação."}
        verification = commands.verify_tool(name, arguments, result)
        return True, result, verification

    try:
        if name == "remember_fact":
            args = _args(arguments, ("subject", "fact"))
            on_execute and on_execute()
            result = memory.remember_fact(args["subject"], args["fact"])
            return True, result, {"verified": True, "evidence": "Memória gravada localmente."}
        if name == "recall_facts":
            args = _args(arguments, ("query",))
            on_execute and on_execute()
            result = memory.recall_facts(args["query"])
            return True, result, {"verified": True, "evidence": "Consulta local."}
        if name == "forget_fact":
            args = _args(arguments, ("subject",))
            subject = str(args["subject"]).strip()
            result = commands._ask(f"esquecer a memória sobre {subject}",
                                   lambda: memory.forget_fact(subject))
            return True, result, {"verified": False, "evidence": "Aguardando confirmação."}
        if name == "set_personality":
            args = _args(arguments, ("style",))
            on_execute and on_execute()
            result = memory.set_preference("personality", args["style"])
            return True, result, {"verified": True, "evidence": "Personalidade persistida."}
        if name == "get_profile":
            _args(arguments or {}, ())
            on_execute and on_execute()
            return True, memory.profile_summary(), {"verified": True, "evidence": "Perfil local."}
        if name == "set_preference":
            args = _args(arguments, ("name", "value"))
            on_execute and on_execute()
            result = memory.set_preference(args["name"], args["value"])
            return True, result, {"verified": True, "evidence": "Preferência local."}
        if name == "add_session_note":
            args = _args(arguments, ("note",))
            on_execute and on_execute()
            result = memory.add_session_note(args["note"])
            return True, result, {"verified": True, "evidence": "Contexto de sessão."}
        if name == "read_audit":
            args = _args(arguments or {}, (), ("limit",))
            on_execute and on_execute()
            return True, memory.recent_audit(args.get("limit", 8)), {"verified": True, "evidence": "Auditoria local."}
        if name == "create_automation":
            args = _args(arguments, ("name", "trigger", "tool_name", "arguments"))
            on_execute and on_execute()
            result = automation.create_automation(args["name"], args["trigger"], args["tool_name"], args["arguments"])
            return True, result, {"verified": True, "evidence": "Automação persistida."}
        if name == "list_automations":
            _args(arguments or {}, ())
            on_execute and on_execute()
            return True, automation.list_automations(), {"verified": True, "evidence": "Lista local."}
        if name == "set_automation_enabled":
            args = _args(arguments, ("name", "enabled"))
            on_execute and on_execute()
            result = automation.set_enabled(args["name"], bool(args["enabled"]))
            return True, result, {"verified": True, "evidence": "Estado da automação atualizado."}
        if name == "delete_automation":
            args = _args(arguments, ("name",))
            name_value = str(args["name"]).strip()
            result = commands._ask(f"remover a automação {name_value}",
                                   lambda: automation.delete_automation(name_value))
            return True, result, {"verified": False, "evidence": "Aguardando confirmação."}
        if name == "ocr_screen":
            _args(arguments or {}, ())
            on_execute and on_execute()
            payload = vision.ocr_screen()
            if not payload["available"]:
                return True, payload["message"], {"verified": False, "evidence": payload["message"]}
            texts = [block["text"] for block in payload["blocks"][:40]]
            result = "OCR: " + (" | ".join(texts) if texts else "(nenhum texto)")
            return True, result, {"verified": True, "evidence": f"motor {payload['engine']}"}
        if name == "list_ui_elements":
            _args(arguments or {}, ())
            on_execute and on_execute()
            payload = vision.list_ui_elements()
            if not payload["available"]:
                return True, payload["message"], {"verified": False, "evidence": payload["message"]}
            labels = [f"{el['name']} ({el['control_type']})" for el in payload["elements"][:30]]
            result = "Controles: " + ("; ".join(labels) if labels else "(nenhum)")
            return True, result, {"verified": True, "evidence": f"motor {payload['engine']}"}
        if name == "locate_on_screen":
            args = _args(arguments, ("description",))
            on_execute and on_execute()
            result = vision.format_locate(vision.locate(args["description"]))
            verified = not result.startswith("Não há OCR") and not result.startswith("Nenhum elemento")
            return True, result, {"verified": verified, "evidence": result}
        if name == "click_by_description":
            args = _args(arguments, ("description",))
            found = vision.locate(args["description"])
            if found["unavailable"]:
                return True, vision.format_locate(found), {"verified": False, "evidence": "visão estruturada ausente"}
            if len(found["matches"]) != 1:
                return True, vision.format_locate(found) + " Clique cancelado: preciso de um único alvo.", {
                    "verified": False, "evidence": "alvo ambíguo ou ausente",
                }
            hit = found["matches"][0]
            result = commands._ask(
                f"clicar em '{hit.get('name') or hit.get('text')}'",
                lambda: vision.click_match(hit),
            )
            return True, result, {"verified": False, "evidence": "Aguardando confirmação."}
        raise ValueError("Ferramenta extra não implementada.")
    except Exception as exc:
        on_error and on_error()
        result = f"Ferramenta recusada ou inválida: {exc}"
        return True, result, {"verified": False, "evidence": result}
