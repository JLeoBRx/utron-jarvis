import autonomous_agent_runtime as r

s = r.snapshot()
assert s['status'] == 'IDLE'

p = r.observe_now()
assert p['runtime_observation'] is True
assert 'windows_state' in p

print('FASE21_SMOKE_OK')
