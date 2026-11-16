"""SAFRA — casca de comparação em PySide6 + QtWebEngine (a alternativa da decisão AD-07).

Faz o mesmo que a prova de conceito em Tauri, para medir as duas com o mesmo instrumento: abre a página local
(`desktop/poc-ui`), põe o ícone na bandeja com menu, recolhe para a bandeja ao fechar, envia notificação, inicia e
encerra o Assistant (SAFRA_POC_BACKEND) e, com `--self-test`, grava o relatório em SAFRA_POC_REPORT.

Uso:  python desktop/poc-qt/shell.py [--self-test]      (requer PySide6-Essentials e PySide6-Addons 6.8)
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

STARTED = time.perf_counter()
UI = Path(__file__).resolve().parents[1] / "poc-ui" / "index.html"

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QAction, QIcon  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

ICON = Path(__file__).resolve().parents[1] / "poc-tauri" / "icons" / "128x128.png"


def backend_health(port: int) -> dict:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=3) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000), "health": body}
    except OSError as exc:
        return {"ok": False, "error": f"sem conexão com o Assistant: {exc}"}


class Window(QWebEngineView):
    def __init__(self, self_test: bool) -> None:
        super().__init__()
        self.self_test = self_test
        self.setWindowTitle("SAFRA — prova de conceito (QtWebEngine)")
        self.resize(960, 640)

    def closeEvent(self, event) -> None:  # noqa: N802 - nome do Qt
        if not self.self_test:
            event.ignore()
            self.hide()                     # fechar a janela recolhe para a bandeja
        else:
            super().closeEvent(event)


def main() -> int:
    self_test = "--self-test" in sys.argv
    port = int(os.environ.get("SAFRA_POC_BACKEND_PORT", "47800"))
    backend = None
    if os.environ.get("SAFRA_POC_BACKEND"):
        backend = subprocess.Popen([os.environ["SAFRA_POC_BACKEND"], *shlex.split(os.environ.get("SAFRA_POC_BACKEND_ARGS", ""))])
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(self_test)
    window = Window(self_test)
    tray_status = "ok"
    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(QIcon(str(ICON)), app)
        tray.setToolTip("SAFRA (prova de conceito)")
        menu = QMenu()
        for label, slot in (("Mostrar o SAFRA", lambda: (window.show(), window.raise_(), window.activateWindow())),
                            ("Enviar notificação de teste", lambda: tray.showMessage("SAFRA", "Notificação de teste da prova de conceito.")),
                            ("Sair", app.quit)):
            action = QAction(label, menu)
            action.triggered.connect(slot)
            menu.addAction(action)
        tray.setContextMenu(menu)
        tray.show()
    else:
        tray_status = "bandeja do sistema indisponível neste ambiente"

    def loaded(ok: bool) -> None:
        if not self_test:
            return
        ready_ms = round((time.perf_counter() - STARTED) * 1000)
        health = backend_health(port)
        deadline = time.monotonic() + 20
        while not health["ok"] and backend is not None and time.monotonic() < deadline:
            time.sleep(0.25)
            health = backend_health(port)
        notification = "ok" if tray is not None and QSystemTrayIcon.supportsMessages() else "notificação indisponível neste ambiente"
        if tray is not None:
            tray.showMessage("SAFRA", "Autoteste da casca")
        report = {"shell": "qtwebengine", "ready_ms": ready_ms, "page_loaded": ok, "tray": tray_status,
                  "notification": notification, "backend": health, "platform": sys.platform}
        line = "SELFTEST_READY " + json.dumps(report, ensure_ascii=False)
        if os.environ.get("SAFRA_POC_REPORT"):
            Path(os.environ["SAFRA_POC_REPORT"]).write_text(line, encoding="utf-8")
        else:
            print(line, flush=True)

    window.loadFinished.connect(loaded)
    window.load(QUrl.fromLocalFile(str(UI)))
    window.show()
    try:
        return app.exec()
    finally:
        if backend is not None:
            backend.terminate()
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()


if __name__ == "__main__":
    sys.exit(main())
