import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import mission_manager, multimodal_context, autonomous_loop

# mission lifecycle
m=mission_manager.enqueue("verificar estado do projeto", priority=70)
assert m["status"]=="QUEUED"
r=mission_manager.start_next(); assert r and r["id"]==m["id"]
mission_manager.finish(m["id"], result="ok")
assert mission_manager.current() is None

ctx=multimodal_context.build(foreground={"process":"Code.exe"}, transcript="verifique o erro", world={"goal":{"text":"debug"}})
assert ctx["foreground"]["process"]=="Code.exe"
assert ctx["voice"]["transcript"]

# loop must not autonomously create a mission by default
res=autonomous_loop.run_once()
assert res["decision"]["action"] in {"IGNORE","MONITOR","SUGGEST"}
print("FASES24_30_SMOKE_OK")
