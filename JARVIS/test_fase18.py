import planning_graph, planner_engine

g = planning_graph.create("investigue e corrija o erro")
assert g["nodes"] and g["edges"]
actions = planning_graph.next_actions()
assert actions
p = planner_engine.create("investigue e corrija o erro")
assert p.graph and p.graph["nodes"]
r = planner_engine.replan("resultado não confirmado")
assert r and r["graph"]["revision"] >= 1
planning_graph.mark("objetivo alcançado", "DONE", "teste")
assert planning_graph.current()["revision"] >= 1
print("FASE 18 OK")
