import capability_graph, tool_registry, action_selector

g=capability_graph.build()
assert g["nodes"] and g["edges"]
s=capability_graph.summary()
assert s["tools"] > 0 and s["capabilities"] > 0
assert tool_registry.validate()["ok"]
assert capability_graph.capabilities_for("ocr_screen")
cs=tool_registry.candidates(["read_screen"], safe_only=True)
assert any(x["tool"] == "ocr_screen" for x in cs)
sel=action_selector.select("leia o erro na tela", {"screen":True})
assert sel
print("FASE 17 OK", s)
