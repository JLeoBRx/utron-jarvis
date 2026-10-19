"""Painel de diagnóstico de voz do JARVIS (HUB principal).

* lista os microfones (leitura em thread de trabalho) e permite escolher outro;
* "TESTAR": as 8 etapas sem fala (inclui ida e volta pelo núcleo e a fala da resposta);
* "TESTAR FALANDO": o usuário diz "Jarvis, que horas são?" e cada etapa é confirmada;
* "CALIBRAR": aprende como o reconhecedor ouve "Jarvis" na voz do usuário;
* contadores ao vivo (blocos lidos, nível, ativações, entregas) só enquanto o painel está aberto.

Nada aqui roda na thread da interface além de pintar: testes, listagem e calibração usam
threads de trabalho e voltam por sinais.
"""
from __future__ import annotations

import threading

from PySide6 import QtCore, QtWidgets

from ..voice.diagnostics import STEPS, run_in_background
from . import theme

MARK = {"OK": "●  OK", "WARN": "●  AVISO", "FAIL": "●  FALHA", "SKIPPED": "○  —", "PENDING": "○  …"}


class VoicePanel(QtWidgets.QWidget):
    _step = QtCore.Signal(object)
    _done = QtCore.Signal(object)
    _devices = QtCore.Signal(object)
    _message = QtCore.Signal(str)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.setObjectName("Panel")
        self._busy = False
        self._cancel = None
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("DIAGNÓSTICO DE VOZ")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        mic_row = QtWidgets.QHBoxLayout()
        self.devices = QtWidgets.QComboBox()
        self.devices.setMinimumWidth(360)
        refresh = self._button("ATUALIZAR", "Ler de novo a lista de microfones")
        refresh.clicked.connect(self.load_devices)
        use = self._button("USAR ESTE", "Trocar o microfone do JARVIS para o selecionado", primary=True)
        use.clicked.connect(self._use_device)
        mic_row.addWidget(QtWidgets.QLabel("Microfone:"))
        mic_row.addWidget(self.devices, 1)
        mic_row.addWidget(refresh)
        mic_row.addWidget(use)
        layout.addLayout(mic_row)
        self.steps = QtWidgets.QTreeWidget()
        self.steps.setHeaderLabels(["ETAPA", "ESTADO", "EVIDÊNCIA"])
        self.steps.setColumnWidth(0, 250)
        self.steps.setColumnWidth(1, 90)
        self.steps.setWordWrap(True)
        self._items = {}
        for key, label in STEPS:
            item = QtWidgets.QTreeWidgetItem([label, MARK["PENDING"], ""])
            self.steps.addTopLevelItem(item)
            self._items[key] = item
        layout.addWidget(self.steps, 1)
        self.prompt = QtWidgets.QLabel("")
        self.prompt.setObjectName("PanelPrompt")
        self.prompt.setWordWrap(True)
        layout.addWidget(self.prompt)
        self.live = QtWidgets.QLabel("")
        self.live.setObjectName("PanelDim")
        layout.addWidget(self.live)
        buttons = QtWidgets.QHBoxLayout()
        self.test = self._button("TESTAR", "As 8 etapas sem precisar falar", primary=True)
        self.test.clicked.connect(lambda: self.run_test(interactive=False))
        self.speak = self._button("TESTAR FALANDO", "Diga \"Jarvis, que horas são?\" quando pedido")
        self.speak.clicked.connect(lambda: self.run_test(interactive=True))
        self.calibrate = self._button("CALIBRAR", "Ensinar como o reconhecedor ouve \"Jarvis\" na sua voz")
        self.calibrate.clicked.connect(self.run_calibration)
        for button in (self.test, self.speak, self.calibrate):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._step.connect(self._on_step, QtCore.Qt.QueuedConnection)
        self._done.connect(self._on_done, QtCore.Qt.QueuedConnection)
        self._devices.connect(self._fill_devices, QtCore.Qt.QueuedConnection)
        self._message.connect(self.prompt.setText, QtCore.Qt.QueuedConnection)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh_live)
        if not getattr(core, "enable_voice", False):
            self.prompt.setText("Voz desativada nesta execução (--no-voice).")
            for button in (self.test, self.speak, self.calibrate, use):
                button.setEnabled(False)

    @staticmethod
    def _button(text: str, tip: str = "", *, primary: bool = False) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        button.setObjectName("HudPrimary" if primary else "HudButton")
        button.setCursor(QtCore.Qt.PointingHandCursor)
        if tip:
            button.setToolTip(tip)
        return button

    # ------------------------------------------------------------ microfones
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self._timer.start()
        self.load_devices()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._timer.stop()
        super().hideEvent(event)

    def load_devices(self) -> None:
        from ..voice.audio import list_input_devices
        backend = str(getattr(self.core.settings(), "mic_backend", "auto") or "auto")
        threading.Thread(target=lambda: self._devices.emit(list_input_devices(backend)),
                         name="jarvis-mic-list", daemon=True).start()

    @QtCore.Slot(object)
    def _fill_devices(self, listing: dict) -> None:
        self.devices.clear()
        current = getattr(getattr(self.core, "voice", None), "device", "")
        for device in listing.get("devices", []):
            label = f"{device['index']}: {device['name']}" + (" (padrão)" if device.get("default") else "")
            self.devices.addItem(label, device)
            if current and device["name"] == current:
                self.devices.setCurrentIndex(self.devices.count() - 1)
        if not listing.get("devices"):
            reason = "; ".join(listing.get("errors", [])) or "nenhum dispositivo de entrada"
            self.devices.addItem(f"nenhum microfone ({reason})", None)

    def _use_device(self) -> None:
        device = self.devices.currentData()
        if not device:
            return
        self.core.settings_manager.update(mic_name=device["name"], mic_index=int(device["index"]))
        self.prompt.setText(f"Microfone escolhido: {device['name']}. Reabrindo a captura…")

    def _refresh_live(self) -> None:
        voice = getattr(self.core, "voice", None)
        if voice is None or not getattr(self.core, "enable_voice", False):
            return
        c = voice.counters()
        state = "capturando" if voice.capturing else (voice.reason or "parado")
        self.live.setText(f"{voice.device or '—'} · {state} · blocos {c['chunks']} · nível {voice.level:.0%} · "
                          f"ativações {c['wakes']} · entregas {c['delivered']} · ecos ignorados {c['echoes']}")

    # ------------------------------------------------------------ testes
    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in (self.test, self.speak, self.calibrate):
            button.setEnabled(not busy and getattr(self.core, "enable_voice", False))

    def run_test(self, *, interactive: bool) -> None:
        if self._busy:
            return
        for key, item in self._items.items():
            item.setText(1, MARK["PENDING"])
            item.setText(2, "")
        self._set_busy(True)
        self.prompt.setText("Testando… " + ("Prepare-se para falar." if interactive else "Sem fala: resposta de teste "
                                                                                       "pela rota da voz."))

        def on_step(step) -> None:
            self._step.emit(step.to_dict())

        if interactive:
            from ..voice.diagnostics import VoiceDiagnostics

            def work() -> None:
                try:
                    report = VoiceDiagnostics(self.core, on_step=on_step).run(
                        interactive=True, listen_seconds=12.0, prompt=self._message.emit)
                except Exception as exc:
                    report = {"overall": "FAIL", "steps": [], "error": str(exc), "seconds": 0}
                self._done.emit(report)

            threading.Thread(target=work, name="jarvis-voice-diagnostics", daemon=True).start()
        else:
            run_in_background(self.core, interactive=False, on_step=on_step, on_done=self._done.emit)

    @QtCore.Slot(object)
    def _on_step(self, step: dict) -> None:
        item = self._items.get(step["key"])
        if item is None:
            return
        item.setText(1, MARK.get(step["status"], step["status"]))
        item.setText(2, step["detail"] + (f"\n→ {step['hint']}" if step.get("hint") and step["status"] != "OK" else ""))
        tone = {"OK": theme.CYAN, "WARN": theme.ALERT, "FAIL": theme.ERROR}.get(step["status"], theme.TEXT_DIM)
        item.setForeground(1, tone)

    @QtCore.Slot(object)
    def _on_done(self, report: dict) -> None:
        self._set_busy(False)
        if report.get("error"):
            self.prompt.setText(f"O diagnóstico falhou: {report['error']}")
            return
        verdict = {"OK": "Voz em ordem.", "WARN": "Voz funcionando com avisos.", "FAIL": "Há falhas na voz."}
        self.prompt.setText(f"{verdict.get(report['overall'], report['overall'])} ({report.get('seconds', 0)} s)")

    def run_calibration(self) -> None:
        if self._busy:
            return
        from ..voice.calibrate import calibrate_live
        self._set_busy(True)

        def work() -> None:
            try:
                result = calibrate_live(self.core, prompt=self._message.emit)
                heard = "; ".join(f"“{t}”" for t in result.transcripts) or "nada"
                added = ", ".join(result.added + result.weak_added) or "nenhuma (as atuais já cobrem a sua pronúncia)"
                self._message.emit(f"Ouvido: {heard}. Formas novas: {added}.")
            except Exception as exc:
                self._message.emit(f"Calibração indisponível: {exc}")
            finally:
                QtCore.QMetaObject.invokeMethod(self, "_calibration_done", QtCore.Qt.QueuedConnection)

        threading.Thread(target=work, name="jarvis-voice-calibration", daemon=True).start()

    @QtCore.Slot()
    def _calibration_done(self) -> None:
        self._set_busy(False)
