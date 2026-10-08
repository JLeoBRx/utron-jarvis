import active_observation

calls=[]
old_sleep=active_observation.time.sleep
active_observation.time.sleep=lambda *_: None

class DummyCommands:
    @staticmethod
    def foreground_info(): return {"process":"code.exe","title":"main.py"}
    @staticmethod
    def capture_screen_image(): return bytearray(b"screen")

class DummyPerception:
    @staticmethod
    def build_core_context(obs, fg, enrich_screen=True):
        return {"foreground":fg,"evidence":{"summary":"main.py aberto"}}

class DummyTemporal:
    @staticmethod
    def observe(thumb, fg, settled=True): return {"changed":True,"stable":True}

import sys
sys.modules['commands']=DummyCommands
sys.modules['perception_engine']=DummyPerception
sys.modules['autonomous_perception']=DummyTemporal
r=active_observation.observe_after_action(emit=lambda *a,**k:calls.append(a[0]))
assert r["active_observation"] is True
assert r["evidence"]["summary"] == "main.py aberto"
assert "active_observation" in calls
active_observation.time.sleep=old_sleep
print("FASE 13 OK")
