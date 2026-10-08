import autonomous_perception

autonomous_perception.reset()
fg={"process":"code.exe","title":"Projeto"}
a=autonomous_perception.observe(b"abc",fg,changed_threshold=True,settled=True)
assert a["changed"] and a["sequence"] == 1
b=autonomous_perception.observe(b"abc",fg,changed_threshold=False,settled=True)
assert b["focus_changed"] is False
c=autonomous_perception.observe(b"xyz",fg,changed_threshold=True,settled=True)
assert c["changed"] and c["reason"] == "mudança visual relevante detectada"
d=autonomous_perception.observe(b"xyz",{"process":"chrome.exe","title":"Navegador"},changed_threshold=False,settled=True)
assert d["focus_changed"] and d["significance"] == 1.0
print("Fase 10 OK")
