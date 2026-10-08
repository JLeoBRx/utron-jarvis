"""
J.A.R.V.I.S. // NEURAL CORE
O cérebro executivo do sistema.

Este módulo não é apenas um seletor de modelo. Ele mantém contexto, recebe
percepções do Observador, decide se há um objetivo acionável, roteia a
inteligência disponível, entrega o objetivo ao agente multietapas e acompanha
planejamento, execução, verificação e recuperação.
"""
from __future__ import annotations
import threading, time, uuid
from collections import deque

import config

STATE_IDLE="IDLE"
STATE_PERCEIVING="PERCEIVING"
STATE_CONTEXT="CONTEXT"
STATE_DECIDING="DECIDING"
STATE_ROUTING="ROUTING"
STATE_PLANNING="PLANNING"
STATE_EXECUTING="EXECUTING"
STATE_VERIFYING="VERIFYING"
STATE_RECOVERY="RECOVERY"
STATE_WAITING="WAITING"
STATE_DONE="DONE"
STATE_ERROR="ERROR"

_LOCK=threading.RLock()
_BUSY=threading.Event()
_ABORT=threading.Event()
_STATE=STATE_IDLE
_GOAL=None
_CONTEXT=deque(maxlen=24)
_HISTORY=deque(maxlen=80)
_LAST_GOALS={}
_LISTENERS=[]


def state():
    with _LOCK: return _STATE

def busy(): return _BUSY.is_set()

def current_goal():
    with _LOCK: return dict(_GOAL) if _GOAL else None

def snapshot():
    with _LOCK:
        return {"state":_STATE,"busy":_BUSY.is_set(),"goal":dict(_GOAL) if _GOAL else None,
                "context":list(_CONTEXT)[-8:],"history":list(_HISTORY)[-12:]}

def subscribe(fn):
    if callable(fn):
        with _LOCK: _LISTENERS.append(fn)

def _emit(kind, **data):
    event={"type":kind,"ts":time.time(),**data}
    with _LOCK: _HISTORY.append(event); listeners=list(_LISTENERS)
    # Ponte oficial Core -> estado visual. A HUD apenas desenha esse estado.
    try:
        import neural_hud_engine
        neural_hud_engine.update_event(event)
    except Exception:
        pass
    for fn in listeners:
        try: fn(event)
        except Exception: pass

def _set_state(value, reason=""):
    global _STATE
    with _LOCK: _STATE=value
    _emit("state", state=value, reason=reason)

def abort():
    _ABORT.set()
    try:
        import agent
        agent.abort()
    except Exception: pass

def _signature(data, fg):
    return "|".join(str(x or "").strip().lower() for x in (fg.get("process"), fg.get("title"), data.get("erro_texto"), data.get("atividade")))[:320]

def _should_act(data, confidence):
    if not bool(data.get("precisa_ajuda")): return False
    if confidence < float(getattr(config,"AGENTIC_MIN_CONFIDENCE",0.68)): return False
    # A percepção de erro claro é prioridade. Outras situações precisam de um objetivo explícito.
    if data.get("erro_visivel"): return True
    action=data.get("acao")
    return isinstance(action,dict) and isinstance(action.get("tool"),str)

def observe(data, foreground, conversation, *, speak=None, emit=None):
    """Entrada do Observador. Retorna True quando o Core assumiu a tarefa."""
    try: confidence=float(data.get("confianca",0))
    except Exception: confidence=0.0
    _set_state(STATE_PERCEIVING,"nova percepção")
    item={"foreground":dict(foreground or {}),"observation":dict(data or {}),"received":time.time()}
    # Evidência estruturada é contexto auxiliar; nunca vira instrução executável por si só.
    evidence = data.get("evidencia_tela")
    if isinstance(evidence, dict):
        item["evidence"] = {
            "summary": str(evidence.get("summary", ""))[:900],
            "context_change": bool(evidence.get("context_change", False)),
            "ocr_count": len((evidence.get("ocr") or {}).get("blocks") or []),
            "ui_count": len((evidence.get("ui") or {}).get("elements") or []),
        }
    with _LOCK: _CONTEXT.append(item)
    _set_state(STATE_CONTEXT,"contexto consolidado")
    # Fase 31/32: fusão multimodal antes da decisão.
    try:
        import multimodal_fusion, intent_engine_v2
        memory_context = ""
        try:
            import memory_v2
            memory_context = str(memory_v2.recall(data.get("resumo") or data.get("erro_texto") or "", limit=3))
        except Exception:
            pass
        fused = multimodal_fusion.build(
            observation=data, foreground=foreground,
            windows_state=item.get("windows_state", {}),
            conversation=conversation, memory_context=memory_context
        )
        item["multimodal_context"] = fused
        _emit("multimodal_context", context=fused)
    except Exception as exc:
        _emit("multimodal_warning", message=str(exc)[:180])
    try:
        import windows_state_adapter
        windows_state = windows_state_adapter.snapshot(include_windows=True)
        item["windows_state"] = windows_state
        _emit("windows_state", state=windows_state)
    except Exception as exc:
        item["windows_state_warning"] = str(exc)[:180]
        _emit("windows_state_warning", message=str(exc)[:180])
    try:
        import world_model
        wm = world_model.update(item)
        if item.get("windows_state"):
            wm = world_model.update_windows_state(item["windows_state"])
        item["world_model"] = wm
        _emit("world_model", snapshot=wm)
    except Exception as exc:
        _emit("world_model_warning", message=str(exc)[:180])
    if data.get("dados_sensiveis_visiveis") or data.get("instrucoes_na_tela"):
        _set_state(STATE_IDLE,"percepção não acionável")
        return False
    # Consolida contexto temporal e infere intenção antes de decidir agir.
    try:
        import proactive_assistance
        proactive = proactive_assistance.evaluate(data, foreground, item.get("context", {}))
        item["proactive"] = proactive.to_dict()
        _emit("proactive", **proactive.to_dict())
        if proactive.action == "SUGGEST" and speak:
            speak("Senhor, detectei algo que pode exigir sua atenção. " + proactive.reason + ".")
    except Exception as exc:
        _emit("proactive_warning", message=str(exc)[:180])
    try:
        import context_engine, intent_engine, decision_engine
        core_context = context_engine.consolidated(item)
        intent = intent_engine_v2.infer(item.get("multimodal_context", core_context)) if "intent_engine_v2" in locals() else intent_engine.infer(core_context)
        item["context"] = core_context
        item["intent"] = intent
        _emit("intent", kind=intent.get("kind"), confidence=intent.get("confidence"), goal=intent.get("goal"))
        confidence = max(confidence, float(intent.get("confidence", 0)))
        decision = decision_engine.evaluate(intent, core_context, data)
        item["decision"] = decision.to_dict()
        _emit("decision", **decision.to_dict())
        if decision.action == "ignore":
            _set_state(STATE_IDLE, decision.reason)
            return False
        if decision.action == "ask":
            _set_state(STATE_WAITING, decision.reason)
            _emit("authorization", objective=decision.objective, reason=decision.reason)
            if speak:
                speak("Senhor, detectei uma situação que merece atenção, mas não tenho confiança suficiente para agir sozinho. Deseja que eu investigue?")
            return False
        if decision.action == "act":
            data = dict(data); data["precisa_ajuda"] = True; data["resumo"] = decision.objective or intent.get("goal", data.get("resumo"))
    except Exception as exc:
        _emit("context_warning", message=str(exc)[:180])
        if not _should_act(data,confidence):
            _set_state(STATE_IDLE,"sem objetivo acionável")
            return False
    sig=_signature(data,foreground); now=time.time(); cooldown=float(getattr(config,"AGENTIC_COOLDOWN",120))
    with _LOCK:
        if now-_LAST_GOALS.get(sig,0)<cooldown:
            _set_state(STATE_IDLE,"objetivo repetido em cooldown"); return False
        _LAST_GOALS[sig]=now
    goal_text=_build_goal(data,foreground)
    try:
        import goal_manager
        g=goal_manager.create(goal_text, source="observer", confidence=confidence, risk=item.get("decision",{}).get("risk","medium"))
        _emit("goal_created", goal=g.to_dict())
    except Exception: pass
    return start(goal_text,conversation,speak=speak,emit=emit,source="observer",context=item)

def _build_goal(data,fg):
    app=data.get("app") or fg.get("process") or "aplicativo atual"
    activity=data.get("atividade") or "atividade desconhecida"
    summary=data.get("resumo") or "há uma situação relevante na tela"
    error=data.get("erro_texto") or ""
    if error:
        return (f"Investigue e, se for seguro e permitido, resolva o problema observado em {app}. "
                f"Contexto: {activity}. Resumo: {summary}. Erro visível: {error}. "
                "Trabalhe em etapas, verifique cada resultado e tente uma alternativa permitida se a primeira falhar. "
                "Não afirme sucesso sem evidência.")
    return (f"Auxilie autonomamente no contexto observado em {app}. Contexto: {activity}. "
            f"Situação: {summary}. Determine um objetivo concreto, aja somente com ferramentas permitidas "
            "e verifique o resultado antes de concluir.")

def start(goal,conversation,*,speak=None,emit=None,source="user",context=None):
    global _GOAL
    if busy(): return False
    _ABORT.clear(); _BUSY.set(); ident=uuid.uuid4().hex[:8]
    with _LOCK: _GOAL={"id":ident,"text":goal,"source":source,"started":time.time()}
    try:
        import world_model
        world_model.set_goal(_GOAL)
    except Exception: pass
    _set_state(STATE_DECIDING,"objetivo recebido")
    # Fase 33/34: inicializa skills e recupera memória semântica/episódica.
    try:
        import skill_system
        skill_system.bootstrap()
        _emit("skills", count=len(skill_system.discover()))
    except Exception as exc:
        _emit("skills_warning", message=str(exc)[:180])
    try:
        import memory_v2
        memory_v2.init()
        recalled = memory_v2.recall(goal, limit=5)
        _emit("memory_recall", count=len(recalled), items=recalled)
        if recalled:
            with _LOCK:
                _CONTEXT.append({"memory_recall": recalled, "received": time.time()})
    except Exception as exc:
        _emit("memory_warning", message=str(exc)[:180])
    _emit("goal", id=ident, goal=goal, source=source)
    if emit:
        try: emit("goal",id=ident,text=goal)
        except Exception: pass
    def worker():
        global _GOAL
        try:
            _set_state(STATE_ROUTING,"selecionando inteligência")
            import intelligence_router
            route_decision = intelligence_router.decide(goal, context or {})
            try:
                import dynamic_router
                route_decision = dynamic_router.decide(goal, context or {}, prefer_local=True)
            except Exception as exc:
                _emit("dynamic_route_warning", message=str(exc)[:180])
            route = route_decision.route
            _emit("route", **route_decision.to_dict())
            _set_state(STATE_PLANNING, f"núcleo {route_decision.model}")
            if emit:
                try: emit("route",route=route)
                except Exception: pass
            import autonomous_agent_runtime
            def timeline(kind,subject,message):
                mapped={"plan":STATE_PLANNING,"validate":STATE_EXECUTING,"observe":STATE_VERIFYING,
                        "error":STATE_RECOVERY,"pause":STATE_WAITING,"done":STATE_DONE}.get(kind,STATE_EXECUTING)
                _set_state(mapped,message)
                _emit("timeline",agent_state=kind,subject=subject,message=message)
                if emit:
                    try: emit("agent",state=kind,text=f"{subject}: {message}")
                    except Exception: pass
            def thinking(): _set_state(STATE_PLANNING,"avaliando próximo passo")
            try:
                import goal_manager
                goal_manager.update(status="EXECUTING")
            except Exception: pass
            def verification(info):
                _set_state(STATE_VERIFYING, str(info.get("reason", "verificando resultado")))
                _emit("verification", **info)
                try:
                    import goal_manager
                    goal_manager.update(evidence=info)
                except Exception: pass
                if emit:
                    try: emit("verification", **info)
                    except Exception: pass
            def recovery(info):
                _set_state(STATE_RECOVERY, str(info.get("reason", "recuperação")))
                _emit("recovery", **info)
                if emit:
                    try: emit("recovery", **info)
                    except Exception: pass
            answer=autonomous_agent_runtime.run(goal,conversation,on_execute=lambda *a, **k: _set_state(STATE_EXECUTING,"ferramenta em execução"),
                on_error=lambda: _set_state(STATE_RECOVERY,"ferramenta falhou"),on_thinking=thinking,
                on_timeline=timeline,on_log=lambda m:_emit("log",message=str(m)),
                on_verification=verification,on_recovery=recovery,
                max_replans=int(getattr(config,"MAX_AGENT_REPLANS",2)), context=context or {})
            if _ABORT.is_set(): _set_state(STATE_IDLE,"cancelado"); return
            _set_state(STATE_DONE,"objetivo encerrado")
            try:
                import world_model
                world_model.set_mission_status("done")
            except Exception: pass
            try:
                import goal_manager
                goal_manager.finish("DONE")
            except Exception: pass
            _emit("result",answer=str(answer or "").strip(), route=route)
            try:
                import memory_engine
                memory_engine.record_episode(goal, route, "done", str(answer or "")[:500])
                memory_engine.record_strategy(goal, "rota=" + route, "usar " + route_decision.model, "done", route_decision.confidence)
            except Exception: pass
            if speak and answer: speak(str(answer).strip())
            return answer
        except Exception as exc:
            _set_state(STATE_ERROR,str(exc)[:200])
            try:
                import world_model
                world_model.set_mission_status("error")
            except Exception: pass
            try:
                import goal_manager
                goal_manager.finish("ERROR")
            except Exception: pass
            _emit("error",message=str(exc)[:500])
            try:
                import memory_engine
                memory_engine.record_episode(goal, route if "route" in locals() else "unknown", "error", str(exc)[:500])
                memory_engine.record_strategy(goal, "rota=" + (route if "route" in locals() else "unknown"), "usar " + (route if "route" in locals() else "unknown"), "error", 0.0)
            except Exception: pass
            if speak: speak("Senhor, o núcleo encontrou uma falha durante a execução.")
        finally:
            _BUSY.clear()
            with _LOCK: _GOAL=None
            if state()!=STATE_IDLE: _set_state(STATE_IDLE,"núcleo em espera")
    threading.Thread(target=worker,name="jarvis-neural-core",daemon=True).start()
    return True

def _route(goal):
    """Compatibilidade: o roteamento real vive no Intelligence Router."""
    import intelligence_router
    return intelligence_router.decide(goal).route

# Fases 24-30: controle explícito do Runtime Autônomo persistente.
def start_autonomous_loop(interval=None):
    import autonomous_loop
    return autonomous_loop.start(interval)

def stop_autonomous_loop():
    import autonomous_loop
    return autonomous_loop.stop()

def autonomous_snapshot():
    import autonomous_loop, mission_manager, long_running_agent
    return {
        "loop": autonomous_loop.snapshot(),
        "missions": mission_manager.snapshot(),
        "long_running": {"running": long_running_agent.running()},
    }

def submit_mission(objective, *, priority=50, source="user", metadata=None):
    import mission_manager
    return mission_manager.enqueue(objective, priority=priority, source=source, metadata=metadata)
