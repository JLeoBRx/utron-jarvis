import proactive_assistance

proactive_assistance.reset()
err = proactive_assistance.evaluate(
    {"erro_visivel": True, "erro_texto": "Traceback: ValueError"},
    {"process": "Code.exe", "title": "main.py"},
)
assert err.action == "SUGGEST"
assert err.confidence >= 0.84

again = proactive_assistance.evaluate(
    {"erro_visivel": True, "erro_texto": "Traceback: ValueError"},
    {"process": "Code.exe", "title": "main.py"},
)
assert again.action == "MONITOR"

sensitive = proactive_assistance.evaluate(
    {"dados_sensiveis_visiveis": True},
    {"process": "Code.exe", "title": "main.py"},
)
assert sensitive.action == "IGNORE"
print("FASE22_SMOKE_OK")
