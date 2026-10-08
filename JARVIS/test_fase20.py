import os
import windows_state_adapter as wsa

s = wsa.snapshot(include_windows=False)
assert isinstance(s, dict)
assert "available" in s
assert isinstance(wsa.diff({}, s), dict)
if os.name != "nt":
    assert s["available"] is False
print("FASE20 OK - adapter estrutural e diff validados")
