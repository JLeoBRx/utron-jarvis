"""Sonda da central 3D num processo próprio (a QApplication precisa nascer já preparada para o QtWebEngine).

Abre a vista 3D de verdade (QtWebEngine + WebGL da máquina), envia sinais, troca de modo e de painel e lê o
que a página está mostrando. Imprime uma linha ``SONDA {json}``. Não inicia o núcleo: nada de microfone,
rede ou robô. Usado por ``tests/test_scene3d.py`` (no Windows nativo e no Linux com Xvfb).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-cena3d-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from ultron.hud.scene3d import availability, prepare_qt
    prepare_qt()
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication(sys.argv[:1])
    ok, reason = availability(None, platform_name=app.platformName())
    result = {"platform": app.platformName(), "available": ok, "reason": reason}
    if not ok:
        print("SONDA " + json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    from ultron.hud.scene3d.view import Scene3DView

    window = QtWidgets.QWidget()
    window.resize(960, 600)
    layout = QtWidgets.QVBoxLayout(window)
    view = Scene3DView(effects=False)            # sem passagem animada: o estado final aparece logo
    requests: list = []
    view.action_requested.connect(requests.append)
    layout.addWidget(view)
    window.show()

    def pump(seconds: float, condition=None) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents(QtCore.QEventLoop.AllEvents, 30)
            if condition is not None and condition():
                return True
        return bool(condition and condition())

    def page_info(attempts: int = 6) -> dict:
        """Estado que a página mostra. Com WebGL por software (CI), a thread da página pode demorar a responder:
        tenta de novo (até ~30 s) em vez de devolver vazio na primeira espera — a conferência não muda."""
        for _ in range(attempts):
            box: dict = {}
            view.page().runJavaScript("JSON.stringify(window.JARVIS ? window.JARVIS.debugInfo() : null)", 0,
                                      lambda value: box.update(value=value))
            pump(5, lambda: "value" in box)
            try:
                info = json.loads(box.get("value") or "null") or {}
            except ValueError:
                info = {}
            if info.get("mode"):
                return info
            pump(0.5)
        return {}

    started = time.monotonic()
    pump(90, lambda: view.is_ready or bool(view.failed))
    result.update(ready=view.is_ready, failed=view.failed, seconds=round(time.monotonic() - started, 1),
                  renderer=view.info.get("renderer", ""))
    if view.is_ready:
        view.on_state({"runtime_state": "IDLE", "boot": {"total": 1, "done": 1}, "active_model": "modelo-teste"})
        view.on_event("SYSTEM_READY", {})
        for _ in range(10):
            view.step(1 / 30)
            pump(0.05)
        result["jarvis"] = page_info()
        view.set_mode("tardis", animate=False)
        view.select_panel("telemetria")
        view.push_room({"available": True, "mode": "processando", "fault": False,
                        "panels": {"telemetria": {"level": 1, "flash": 0, "fault": 0, "running": 1, "last": ""}}})
        pump(4)
        result["tardis"] = page_info()
        view.page().runJavaScript("document.querySelector('#views button[data-view=sair]').click()")
        pump(10, lambda: bool(requests))
        result["requests"] = list(requests)
        result["js_errors"] = view.js_errors
        result["failed_after"] = view.failed
    view.dispose()
    window.close()
    print("SONDA " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
