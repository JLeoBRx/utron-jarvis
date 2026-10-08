import capability_model
caps = capability_model.infer("leia o texto do erro na tela e encontre o botão continuar", {"visual": True})
names = [c["name"] for c in caps]
assert "read_screen" in names
assert "understand_ui" in names
assert "interact_ui" in names
assert "ocr_screen" in capability_model.tools_for(["read_screen"])
assert "click_by_description" in capability_model.tools_for(["interact_ui"])
print("FASE 15 OK")
