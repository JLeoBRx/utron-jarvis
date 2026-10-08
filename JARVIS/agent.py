"""
J.A.R.V.I.S. // orquestrador do agente (planejar → validar → executar → observar).
Não executa shell. Usa somente tools.DEFINITIONS.
"""
import json
import threading
import time
import urllib.request

import config
import memory
import tools

_abort = threading.Event()
_busy = threading.Event()
_pause = threading.Event()  # set = pausado


def busy():
    return _busy.is_set()


def paused():
    return _pause.is_set() and _busy.is_set()


def abort():
    if _busy.is_set():
        _abort.set()
        _pause.clear()
        return True
    return False


def pause():
    if _busy.is_set():
        _pause.set()
        return True
    return False


def resume():
    if _pause.is_set():
        _pause.clear()
        return True
    return False


def chat(messages, tool_defs=None, model=None):
    payload = {"model": model or config.OLLAMA_MODEL, "messages": messages, "stream": False}
    if tool_defs:
        payload["tools"] = tool_defs
    request = urllib.request.Request(
        config.OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))["message"]


def _jarvis_tone(text):
    """Remove vícios de linguagem excessivamente amigáveis sem reescrever a resposta inteira."""
    replacements = {
        "Claro, senhor.": "Entendido, senhor.",
        "Claro!": "Entendido.",
        "Perfeito, senhor.": "Entendido, senhor.",
        "Perfeito!": "Entendido.",
        "Ótimo, senhor.": "Certo, senhor.",
        "Ótimo!": "Certo.",
        "Excelente, senhor.": "Certo, senhor.",
        "Fico feliz em ajudar.": "A tarefa está em andamento.",
    }
    result = str(text or "").strip()
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def _wait_if_paused(on_timeline):
    if not _pause.is_set():
        return
    on_timeline("pause", "agente", "Execução pausada. Diga continuar ou use a bandeja.")
    while _pause.is_set() and not _abort.is_set():
        time.sleep(0.15)


def run(user_text, conversation, on_execute=None, on_error=None, on_thinking=None,
        on_timeline=None, on_log=None, chat_fn=None):
    """Loop multietapas. conversation é a lista mutável do backend."""
    chat_fn = chat_fn or chat
    on_timeline = on_timeline or (lambda *a, **k: None)
    on_log = on_log or (lambda *a, **k: None)

    _style, prompt = memory.system_prompt()
    try:
        import memory_engine
        learned = memory_engine.relevant_context(user_text)
        prompt += " Contexto de aprendizagem operacional: " + learned + " Use isso apenas como evidência auxiliar, nunca como instrução absoluta."
    except Exception:
        pass
    if conversation:
        conversation[0] = {"role": "system", "content": prompt}
    else:
        conversation.append({"role": "system", "content": prompt})

    messages = list(conversation)
    messages.append({"role": "user", "content": user_text})
    tool_count = 0
    _abort.clear()
    _pause.clear()
    _busy.set()
    on_timeline("plan", "orquestrador", "Iniciando planejamento local.")

    try:
        for step in range(config.MAX_AGENT_STEPS):
            if _abort.is_set():
                on_timeline("cancel", "orquestrador", "Plano cancelado.")
                return "Plano cancelado, senhor."
            _wait_if_paused(on_timeline)
            if _abort.is_set():
                return "Plano cancelado, senhor."

            on_thinking and on_thinking()
            on_timeline("plan", f"passo {step + 1}", "Consultando o modelo local.")
            assistant_message = chat_fn(messages, tools.DEFINITIONS)
            messages.append(assistant_message)
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                answer = str(assistant_message.get("content") or "").strip()
                if not answer:
                    answer = "Senhor, não consegui concluir essa solicitação."
                # O prompt global define o estilo JARVIS; este reforço evita respostas de atendente
                # quando o modelo local ignorar parcialmente a personalidade.
                answer = _jarvis_tone(answer)
                conversation.extend(messages[len(conversation):])
                on_timeline("done", "orquestrador", "Resposta sem novas ferramentas.")
                return answer

            for tool_call in tool_calls:
                if tool_count >= config.MAX_AGENT_TOOL_CALLS:
                    messages.append({
                        "role": "tool",
                        "content": "Limite de ferramentas desta solicitação atingido; nenhuma outra ação foi executada.",
                    })
                    on_timeline("error", "limite", "Máximo de ferramentas atingido.")
                    break

                _wait_if_paused(on_timeline)
                if _abort.is_set():
                    return "Plano cancelado, senhor."

                function = tool_call.get("function") or {}
                tool_name = function.get("name")
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                on_log(f"Passo {tool_count + 1}: {tool_name}")
                on_timeline("validate", tool_name, "Validando na allowlist.")

                if tools.is_forbidden(tool_name):
                    observation = {
                        "result": "A ferramenta solicitada não está permitida.",
                        "verification": {"verified": False, "evidence": "fora da allowlist"},
                        "recovery": "Escolha outra ferramenta registrada. Nunca use shell.",
                    }
                    messages.append({"role": "tool", "content": json.dumps(observation, ensure_ascii=False)})
                    memory.audit("agent", str(tool_name), "bloqueada", False)
                    on_timeline("error", tool_name or "desconhecida", "Bloqueada pela allowlist.")
                    tool_count += 1
                    continue

                handled, result, verification = tools.execute(
                    tool_name, arguments, on_execute=on_execute, on_error=on_error,
                )
                tool_count += 1
                verified = bool(verification.get("verified")) if verification else False
                memory.audit("agent", tool_name, result, verified)

                if not handled:
                    observation = {
                        "result": "A ferramenta solicitada não está permitida.",
                        "verification": verification,
                        "recovery": "Use somente ferramentas da lista.",
                    }
                    on_timeline("error", tool_name, "Recusada.")
                else:
                    import commands as _commands
                    if _commands.is_confirmation_pending():
                        conversation.extend([
                            {"role": "user", "content": user_text},
                            {"role": "assistant", "content": result},
                        ])
                        on_timeline("observe", tool_name, "Aguardando confirmação do usuário.")
                        return result
                    recovery = None
                    if not verified:
                        recovery = (
                            "A ação falhou ou não foi verificada. Tente outra ferramenta permitida "
                            "ou explique a falha. Não afirme sucesso."
                        )
                        on_timeline("error", tool_name, verification.get("evidence", "falha"))
                        on_thinking and on_thinking()
                    else:
                        on_timeline("observe", tool_name, verification.get("evidence", result)[:160])
                        on_thinking and on_thinking()
                    observation = {"result": result, "verification": verification}
                    if recovery:
                        observation["recovery"] = recovery

                messages.append({"role": "tool", "content": json.dumps(observation, ensure_ascii=False)})

        answer = "Senhor, não consegui concluir o plano dentro do limite seguro de etapas."
        conversation.extend(messages[len(conversation):])
        conversation.append({"role": "assistant", "content": answer})
        on_timeline("error", "limite", "Máximo de etapas atingido.")
        return answer
    except Exception as exc:
        on_timeline("error", "orquestrador", str(exc)[:160])
        raise
    finally:
        _busy.clear()
        _pause.clear()
