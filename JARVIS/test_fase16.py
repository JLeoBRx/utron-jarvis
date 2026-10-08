import capability_discovery

cat = capability_discovery.catalog()
assert cat
assert capability_discovery.by_tool("ocr_screen")
assert any(x["tool"] == "ocr_screen" and "read_screen" in x["capabilities"] for x in cat)
assert any(x["tool"] == "click_by_description" and "interact_ui" in x["capabilities"] for x in cat)
assert capability_discovery.tools_for_capability("read_screen")
report = capability_discovery.validate()
assert report["ok"], report
print("FASE16 OK", report["tool_count"], report["capability_links"])
