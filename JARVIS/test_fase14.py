import sys, types
fake_tools = types.SimpleNamespace(DEFINITIONS=[
    {"function":{"name": n}} for n in [
        "ocr_screen","list_ui_elements","locate_on_screen","click_by_description",
        "open_app","open_url","search_web","search_files","take_screenshot",
        "system_status","wait_seconds","control_volume","control_media",
        "remember_fact","recall_facts"
    ]
])
sys.modules["tools"] = fake_tools
import action_selector
r = action_selector.select("leia o texto do erro na tela e encontre o botão continuar", {"visual": True}, limit=5)
names = [x.name for x in r]
assert "ocr_screen" in names
assert any(x in names for x in ("locate_on_screen", "list_ui_elements", "click_by_description"))
assert all(0.0 <= x.score <= 1.0 for x in r)
print("FASE 14 OK")
