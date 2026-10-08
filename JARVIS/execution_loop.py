"""J.A.R.V.I.S. // EXECUTION LOOP
Ciclo: planejar -> executar -> observar -> verificar -> concluir ou recuperar.
"""
from __future__ import annotations
import planner_engine
import verification_engine
import recovery_engine
import state_verifier
import agent
import action_selector


def run(goal, conversation, *, on_execute=None, on_error=None, on_thinking=None,
        on_timeline=None, on_log=None, max_replans=2, on_verification=None, on_recovery=None, context=None):
    on_timeline = on_timeline or (lambda *a, **k: None)
    on_log = on_log or (lambda *a, **k: None)
    on_verification = on_verification or (lambda *a, **k: None)
    on_recovery = on_recovery or (lambda *a, **k: None)
    try:
        import memory_engine
        memory_engine.init()
        learned = memory_engine.relevant_context(goal)
        on_log("Memória operacional consultada antes do planejamento.")
    except Exception:
        memory_engine = None
        learned = ""
    plan = planner_engine.create(goal)
    candidates = action_selector.select(goal, context or {}, limit=5)
    guidance = action_selector.guidance(goal, context or {}, limit=5)
    on_log("Seleção de ferramentas: " + ", ".join(c.name for c in candidates) if candidates else "Nenhuma ferramenta priorizada.")
    on_timeline("plan", "planner", f"Plano {plan.id} criado com estratégia adaptativa.")
    last_failure = ""
    for revision in range(max_replans + 1):
        if revision:
            planner_engine.replan(last_failure or "resultado não confirmado")
            on_timeline("plan", "planner", f"Replanejando após verificação negativa. Revisão {revision}.")
        planner_engine.set_status("EXECUTING")
        events = {"failed": False, "last": "", "tool": "", "evidence": ""}

        def timeline(kind, subject, message):
            if kind == "validate":
                events["tool"] = subject
                planner_engine.step_started(subject)
            elif kind == "observe":
                events["evidence"] = message
                planner_engine.step_result(True, message)
            elif kind == "error":
                events["failed"] = True; events["last"] = message
                planner_engine.step_result(False, message)
            elif kind == "pause": planner_engine.set_status("WAITING")
            elif kind == "done": planner_engine.set_status("VERIFYING")
            on_timeline(kind, subject, message)

        try:
            guided_goal = (goal if not last_failure else (
                    f"{goal}\n\nRECUPERAÇÃO: a tentativa anterior não foi confirmada. "
                    f"Evidência: {last_failure}. Reavalie a estratégia, escolha uma alternativa permitida "
                    "e verifique o estado final antes de concluir."
                )) + "\n\nORIENTAÇÃO DE SELEÇÃO DE FERRAMENTAS:\n" + guidance
            answer = agent.run(
                guided_goal,
                conversation, on_execute=on_execute, on_error=on_error,
                on_thinking=on_thinking, on_timeline=timeline, on_log=on_log,
            )
            if agent.paused():
                planner_engine.set_status("WAITING")
                return answer

            # Fase 13: depois da execução, o JARVIS observa ativamente o desktop novamente.
            active = {}
            try:
                import active_observation
                active = active_observation.observe_after_action(emit=lambda kind, **info: on_log("Percepção ativa: " + kind))
                events["active_observation"] = active
                evidence = (active.get("evidence") or {}).get("summary", "") if isinstance(active, dict) else ""
                if evidence:
                    events["evidence"] = evidence
                on_timeline("observe", "active_observation", "estado posterior capturado após a ação")
            except Exception as exc:
                on_log("Percepção ativa indisponível: " + str(exc)[:180])

            verification = verification_engine.verify(
                timeline_failed=events["failed"], answer=answer, goal=goal,
                context=planner_engine.current(),
            ).to_dict()
            # Fase 12: uma segunda camada compara o estado esperado com o estado conhecido.
            try:
                import world_model
                world = world_model.snapshot()
            except Exception:
                world = {}
            expected = state_verifier.expected_from_transition(goal, events.get("tool", ""), events.get("evidence", ""), verification)
            active_evidence = events.get("evidence", "")
            if isinstance(active, dict):
                active_evidence = active_evidence or str((active.get("evidence") or {}).get("summary", ""))
            state_check = state_verifier.check(expected, world=world, evidence=active_evidence, timeline_failed=events["failed"]).to_dict()
            verification["state_check"] = state_check
            if verification.get("status") == "VERIFIED" and state_check["status"] != "VERIFIED":
                verification["status"] = state_check["status"]
                verification["confidence"] = min(float(verification.get("confidence", 0.0)), float(state_check["confidence"]))
                verification["evidence"] = state_check["observed"] or verification.get("evidence", "")
                verification["reason"] = state_check["reason"]
            on_verification(verification)
            on_timeline("verification", "verifier", f"{verification['status']}: {verification['reason']}")
            decision = recovery_engine.decide(verification, revision, max_replans).to_dict()
            on_recovery(decision)

            if decision["action"] == "finish":
                planner_engine.finish(True)
                on_timeline("done", "verifier", "Objetivo confirmado por evidência suficiente.")
                if memory_engine:
                    try:
                        memory_engine.record_episode(goal, "adaptive", "verified", verification.get("evidence", ""))
                        memory_engine.record_strategy(goal, learned, "estratégia que levou à verificação", "verified", verification.get("confidence", 1.0))
                    except Exception:
                        pass
                return answer
            if decision["action"] == "replan":
                last_failure = verification["evidence"] or events["last"] or "resultado não confirmado"
                planner_engine.set_status("REPLANNING")
                on_timeline("recovery", "recovery", decision["reason"])
                continue

            planner_engine.finish(False)
            on_timeline("error", "verifier", decision["reason"])
            return answer
        except Exception as exc:
            last_failure = str(exc)[:500]
            verification = verification_engine.Verification(False, 0.98, "FAILED", last_failure, "exceção durante execução", True).to_dict()
            on_verification(verification)
            decision = recovery_engine.decide(verification, revision, max_replans).to_dict()
            on_recovery(decision)
            if decision["action"] == "replan":
                planner_engine.set_status("REPLANNING")
                on_timeline("recovery", "recovery", decision["reason"])
                continue
            planner_engine.finish(False)
            raise
    planner_engine.finish(False)
    if memory_engine:
        try:
            memory_engine.record_episode(goal, "adaptive", "unconfirmed", last_failure)
            memory_engine.record_strategy(goal, learned, "tentativa adaptativa sem confirmação", "unconfirmed", 0.0)
        except Exception:
            pass
    return "Senhor, o objetivo não foi confirmado dentro do limite seguro de recuperação."
