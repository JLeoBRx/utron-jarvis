import neural_hud_engine as h
import voice_pipeline as v
import proactive_voice as p
import skill_visualizer as sv

h.reset()
h.update_event({"type":"state","state":"EXECUTING"})
s=h.snapshot()
assert "AGENT" in s["active_modules"] and "WINDOWS" in s["active_modules"]
h.update_event({"type":"route","route":"OPENAI"})
assert "GPT" in h.snapshot()["active_modules"]
assert p.allow("x", 9999) is True
assert p.allow("x", 9999) is False
assert "VISION" in sv.active_skill_modules([{"name":"vision"}])
v.begin_speaking("teste")
assert v.snapshot()["speaking"] is True
v.interrupt()
assert v.should_interrupt() is True
v.end_speaking()
print("FASES36_40_SMOKE_OK")
