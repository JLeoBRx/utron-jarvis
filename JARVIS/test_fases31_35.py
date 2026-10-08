import multimodal_fusion, intent_engine_v2, skill_system, memory_v2, dynamic_router

ctx = multimodal_fusion.build(
    observation={"erro_visivel": True, "erro_texto": "ValueError", "evidencia_tela":{"summary":"traceback", "context_change":True}},
    foreground={"process":"Code.exe","title":"main.py"},
    windows_state={"active":{"process":"Code.exe"},"windows":[{}]},
    goal="investigar erro",
    memory_context="estratégia anterior"
)
assert ctx["error"]["visible"] is True
intent = intent_engine_v2.infer(ctx)
assert intent["kind"] == "troubleshoot" and intent["actionable"]
skill_system.bootstrap()
assert skill_system.find_for("read_screen")
route = dynamic_router.decide("investigue e corrija o erro", ctx, prefer_local=True)
assert route.route == "OLLAMA_LOCAL"
memory_v2.init()
memory_v2.remember_episode("teste fase 35", "ctx", "DONE", 1.0)
assert memory_v2.recall("teste", 2)
print("FASES31_35_SMOKE_OK")
