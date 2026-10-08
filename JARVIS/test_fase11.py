import world_model

def test_world_model_updates():
    world_model.reset()
    snap=world_model.update({
        "foreground":{"process":"code.exe","title":"main.py - Projeto"},
        "observation":{"atividade":"desenvolvimento Python","erro_visivel":True,"erro_texto":"Traceback: teste","confianca":0.91},
        "evidence":{"context_change":True}
    })
    kinds={e["kind"] for e in snap["entities"]}
    assert "application" in kinds and "window" in kinds and "activity" in kinds and "error" in kinds
    assert snap["relations"]

def test_goal_state():
    world_model.reset()
    snap=world_model.set_goal({"id":"abc","text":"corrigir erro"})
    assert snap["mission"]["status"] == "active"
    world_model.set_mission_status("done")
    assert world_model.snapshot()["mission"]["status"] == "done"

if __name__ == "__main__":
    test_world_model_updates(); test_goal_state(); print("Fase 11 OK")
