"""J.A.R.V.I.S. // ACTIVE OBSERVATION
Percepção sob demanda após uma ação. Não executa ações e não interpreta a tela como comando.
"""
from __future__ import annotations
import time


def observe_after_action(*, settle=0.7, timeout=3.0, emit=None):
    """Captura novamente o estado do desktop após uma ação e devolve evidência estruturada."""
    emit = emit or (lambda *a, **k: None)
    time.sleep(max(0.0, float(settle)))
    deadline = time.time() + max(0.2, float(timeout))
    last = None
    while time.time() < deadline:
        try:
            import commands, perception_engine, autonomous_perception
            fg = commands.foreground_info()
            image = commands.capture_screen_image()
            try:
                # Pequena representação é suficiente para detectar mudança temporal.
                thumb = image.resize((96, 54)) if hasattr(image, "resize") else image
                temporal = autonomous_perception.observe(thumb, fg, settled=True)
            finally:
                del image
            package = perception_engine.build_core_context({}, fg, enrich_screen=True)
            package["temporal"] = temporal
            package["active_observation"] = True
            package["timestamp"] = time.time()
            try:
                import world_model
                wm = world_model.update(package)
                package["world_model"] = wm
            except Exception as exc:
                package["world_model_error"] = str(exc)[:180]
            last = package
            emit("active_observation", package=package)
            # Uma percepção estruturada já é suficiente; não precisamos insistir em capturas.
            return package
        except Exception as exc:
            last = {"active_observation": True, "error": str(exc)[:240], "timestamp": time.time()}
            emit("active_observation_error", message=last["error"])
            time.sleep(0.25)
    return last or {"active_observation": True, "error": "não foi possível observar o estado posterior"}
