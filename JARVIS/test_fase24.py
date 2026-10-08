import autonomous_loop, time
assert autonomous_loop.start(interval=0.2) is True
assert autonomous_loop.start(interval=0.2) is False
time.sleep(0.25)
assert autonomous_loop.stop() is True
print("FASE24_SMOKE_OK")
