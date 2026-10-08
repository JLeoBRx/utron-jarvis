import verification_engine, recovery_engine, planner_engine

v=verification_engine.verify(answer="concluído")
assert v.status == "UNCONFIRMED"
r=recovery_engine.decide(v.to_dict(),0,2)
assert r.action == "replan"
v2=verification_engine.verify(tool_result={"verified":True,"evidence":"arquivo salvo e reaberto"})
assert v2.success and v2.status == "VERIFIED"
r2=recovery_engine.decide(v2.to_dict(),1,2)
assert r2.action == "finish"
p=planner_engine.create("investigue e corrija o erro do projeto")
assert len(p.steps) >= 2
print("FASE7 TESTS OK")
