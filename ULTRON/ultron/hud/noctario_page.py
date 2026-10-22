"""Página NOCTÁRIO — o robô seguidor de linha visto e comandado do PC.

* Mostra só o que o robô REPORTOU: estado confirmado (e o pedido em andamento: "aguardando confirmação" ou
  "sem confirmação do robô"), calibração, os 8 sensores, posição da linha, erro e correção do PD, PWM de
  cada motor, velocidade alvo, cruzamentos, recuperação, última falha, voltas gravadas e alertas.
  Sem conexão: "SEM CONEXÃO — nenhum dado do robô", e nada é desenhado como se fosse do robô.
* SIMULADOR: faixa âmbar permanente "SIMULADOR — não é o robô".
* PARADA DE EMERGÊNCIA sempre visível (e F12 em qualquer página): direto no transporte, sem fila. A parada
  pelo Bluetooth NÃO substitui o botão físico que corta a alimentação dos motores.
* Partida, calibração e parâmetros passam pelo JARVIS (permissão "comandos ao robô": confirmação), com os
  limites do protocolo nos campos. A interface não roda o PD: o controle é do firmware.
* Gráficos a no máximo 20 quadros/s, só com a página visível e o robô conectado.
"""
from __future__ import annotations

import threading
import time

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ..noctario.protocol import PARAMS, fmt
from . import theme

ACCENT = "#3DFFA8"
STYLE = theme.PANEL_STYLESHEET + """
QLabel#NoctTitle { color: #3DFFA8; font-size: 11pt; letter-spacing: 3px; }
QLabel#NoctState { color: #F0FAFF; font-size: 20pt; letter-spacing: 3px; }
QLabel#NoctDim { color: #7F9BB7; font-size: 9pt; }
QLabel#NoctValue { color: #DCEEFF; font-size: 10pt; }
QLabel#NoctBanner { padding: 6px 10px; font-size: 9pt; letter-spacing: 2px; border-radius: 3px; }
QFrame#NoctSide { background: #071426; border-left: 1px solid rgba(61, 255, 168, 60); }
QPushButton#NoctButton { background: #050E1C; color: #A8FFD9; border: 1px solid rgba(61, 255, 168, 90);
    border-radius: 4px; padding: 6px 10px; font-size: 8pt; letter-spacing: 1px; }
QPushButton#NoctButton:hover { border-color: rgba(61, 255, 168, 200); color: #F0FFF8; }
QPushButton#NoctButton:disabled { color: #3D5873; border-color: rgba(7, 89, 133, 90); }
QPushButton#NoctPrimary { background: rgba(61, 255, 168, 40); color: #F0FFF8; border: 1px solid rgba(61, 255, 168, 200);
    border-radius: 4px; padding: 7px 12px; font-size: 9pt; letter-spacing: 2px; }
QPushButton#NoctPrimary:disabled { color: #3D5873; background: rgba(7, 89, 133, 30); border-color: rgba(7, 89, 133, 90); }
QPushButton#NoctStop { background: #B3122E; color: #FFFFFF; border: 2px solid #FF5D73; border-radius: 6px;
    padding: 14px 10px; font-size: 13pt; font-weight: bold; letter-spacing: 3px; }
QPushButton#NoctStop:hover { background: #D7193A; }
QPushButton#NoctStop:pressed { background: #8A0D23; }
"""
SETTINGS_KEYS = ("kp", "kd", "base", "max", "minpwm", "accel", "decel", "adapt", "cross", "hb", "onlink", "tel",
                 "xact", "flip", "ldir", "rdir")
CHOICE_LABELS = {("onlink", "stop"): "parar", ("onlink", "continue"): "terminar o percurso",
                 ("xact", 1): "nível alto", ("xact", 0): "nível baixo", ("flip", 0): "não", ("flip", 1): "sim",
                 ("ldir", 1): "normal", ("ldir", -1): "invertido", ("rdir", 1): "normal", ("rdir", -1): "invertido"}
RESULT_LABELS = {"concluida": "concluída", "linha_perdida": "linha perdida", "interrompida": "interrompida",
                 "emergencia": "parada de emergência"}


def _label(text: str = "", name: str = "NoctDim") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _button(text: str, tip: str = "", *, primary: bool = False) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName("NoctPrimary" if primary else "NoctButton")
    button.setCursor(QtCore.Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    return button


class SensorBars(QtWidgets.QWidget):
    """Os 8 sensores calibrados (0–1000), a posição da linha (0–7000) e o sensor de cruzamento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[int] = []
        self.pos: int | None = None
        self.lost = False
        self.setMinimumHeight(120)

    def set_reading(self, values: list[int], pos: int | None, lost: bool) -> None:
        self.values, self.pos, self.lost = list(values or []), pos, lost
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        rect = self.rect().adjusted(8, 8, -8, -22)
        p.fillRect(self.rect(), QtGui.QColor("#050E1C"))
        if not self.values:
            p.setPen(QtGui.QColor("#7F9BB7"))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, "SEM CONEXÃO — nenhum dado do robô")
            return
        count = len(self.values)
        width = rect.width() / count
        for i, value in enumerate(self.values):
            h = rect.height() * max(0, min(1000, value)) / 1000
            bar = QtCore.QRectF(rect.left() + i * width + 4, rect.bottom() - h, width - 8, h)
            color = QtGui.QColor(ACCENT if value >= 200 else "#1E6E57")
            p.fillRect(bar, color)
            p.setPen(QtGui.QColor("#7F9BB7"))
            p.drawText(QtCore.QRectF(rect.left() + i * width, rect.bottom() + 2, width, 16), QtCore.Qt.AlignCenter,
                       str(value))
        if self.pos is not None:
            x = rect.left() + (self.pos / 7000.0) * (rect.width() - width) + width / 2
            pen = QtGui.QPen(QtGui.QColor("#FF5D73" if self.lost else "#FFFFFF"), 2)
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            p.drawText(QtCore.QPointF(x + 4, rect.top() + 12), "LINHA PERDIDA" if self.lost else f"{self.pos}")


def _pen(color: str) -> QtGui.QPen:
    pen = QtGui.QPen(QtGui.QColor(color), 1)
    pen.setCosmetic(True)
    return pen


class TelemetryGraph(QtWidgets.QWidget):
    """Últimos segundos da telemetria: posição da linha/erro, PWM dos motores e mapa dos 8 sensores."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples: list[dict] = []
        self.window = 20.0
        self.message = "SEM CONEXÃO — nenhum dado do robô"
        self.setMinimumHeight(260)

    def set_samples(self, samples: list[dict], message: str = "") -> None:
        self.samples = samples
        self.message = message
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QtGui.QColor("#050E1C"))
        if not self.samples:
            p.setPen(QtGui.QColor("#7F9BB7"))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, self.message or "sem telemetria")
            return
        rect = self.rect().adjusted(46, 10, -10, -10)
        third = rect.height() / 3
        panels = (QtCore.QRectF(rect.left(), rect.top(), rect.width(), third - 8),
                  QtCore.QRectF(rect.left(), rect.top() + third, rect.width(), third - 8),
                  QtCore.QRectF(rect.left(), rect.top() + 2 * third, rect.width(), third - 4))
        now = self.samples[-1]["at"]
        start = now - self.window

        def x_of(at: float) -> float:
            return panels[0].left() + (at - start) / self.window * panels[0].width()

        grid = QtGui.QPen(QtGui.QColor(0, 217, 255, 30))
        grid.setCosmetic(True)
        for panel, title in zip(panels, ("POSIÇÃO DA LINHA (0–7000)", "PWM ESQUERDO / DIREITO", "SENSORES")):
            p.setPen(grid)
            p.drawRect(panel)
            p.setPen(QtGui.QColor("#7F9BB7"))
            p.drawText(QtCore.QPointF(panel.left() + 6, panel.top() + 12), title)
        # posição da linha (centro tracejado) e cruzamentos
        center_y = panels[0].center().y()
        dash = QtGui.QPen(QtGui.QColor(127, 155, 183, 120), 1, QtCore.Qt.DashLine)
        p.setPen(dash)
        p.drawLine(QtCore.QPointF(panels[0].left(), center_y), QtCore.QPointF(panels[0].right(), center_y))
        line = QtGui.QPolygonF()
        for s in self.samples:
            if s.get("pos") is not None:
                y = panels[0].bottom() - (s["pos"] / 7000.0) * panels[0].height()
                line.append(QtCore.QPointF(x_of(s["at"]), y))
        p.setPen(_pen(ACCENT))                              # caneta de 1 px: o caminho rápido do QPainter
        p.drawPolyline(line)
        previous_x = None
        p.setPen(_pen("#FFB347"))
        for s in self.samples:
            if previous_x is not None and s.get("x") is not None and s["x"] != previous_x:
                xx = x_of(s["at"])
                p.drawLine(QtCore.QPointF(xx, panels[0].top()), QtCore.QPointF(xx, panels[2].bottom()))
            previous_x = s.get("x")
        # PWM
        for key, color in (("l", "#67F3FF"), ("r", "#FFB347")):
            poly = QtGui.QPolygonF()
            for s in self.samples:
                if s.get(key) is not None:
                    y = panels[1].center().y() - (s[key] / 255.0) * panels[1].height() / 2
                    poly.append(QtCore.QPointF(x_of(s["at"]), y))
            p.setPen(_pen(color))
            p.drawPolyline(poly)
        # mapa dos 8 sensores: uma imagem 8 × N (uma coluna por amostra) desenhada de uma vez
        columns = [list((s.get("s") or [])[:8]) for s in self.samples]
        columns = [c + [0] * (8 - len(c)) for c in columns]
        shade = np.clip(np.asarray(columns, dtype=np.float32).T, 0, 1000) / 1000.0
        pixels = np.ascontiguousarray(0xFF000000 | ((61 * shade).astype(np.uint32) << 16)
                                      | ((255 * shade).astype(np.uint32) << 8) | (168 * shade).astype(np.uint32),
                                      dtype=np.uint32)
        data = pixels.tobytes()
        image = QtGui.QImage(data, pixels.shape[1], pixels.shape[0], pixels.shape[1] * 4,
                             QtGui.QImage.Format_RGB32).copy()
        left, right = x_of(self.samples[0]["at"]), x_of(self.samples[-1]["at"])
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)
        p.drawImage(QtCore.QRectF(left, panels[2].top(), max(1.0, right - left), panels[2].height()), image)
        p.setPen(grid)
        for i in range(1, 8):
            y = panels[2].top() + i * panels[2].height() / 8
            p.drawLine(QtCore.QPointF(panels[2].left(), y), QtCore.QPointF(panels[2].right(), y))


class _Runner(QtCore.QObject):
    done = QtCore.Signal(str, object)

    def run(self, key: str, fn, *args, **kwargs) -> None:
        def work() -> None:
            try:
                value = fn(*args, **kwargs)
            except Exception as exc:                      # vira mensagem na tela
                value = exc
            self.done.emit(key, value)

        threading.Thread(target=work, name=f"ultron-noctario-ui-{key}", daemon=True).start()


class NoctarioPage(QtWidgets.QWidget):
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.service = core.noctario
        self.setObjectName("Panel")
        self.setStyleSheet(STYLE)
        self.runner = _Runner(self)
        self.runner.done.connect(self._done, QtCore.Qt.QueuedConnection)
        self._fields: dict[str, QtWidgets.QWidget] = {}
        self._loaded_params: dict = {}
        self._runs: list[dict] = []
        self.frames = 0
        self._build()
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------ montagem
    def _build(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(14, 10, 0, 10)
        root.setSpacing(12)
        main = QtWidgets.QVBoxLayout()
        main.setSpacing(8)
        self.banner = QtWidgets.QLabel()
        self.banner.setObjectName("NoctBanner")
        main.addWidget(self.banner)
        head = QtWidgets.QHBoxLayout()
        state_box = QtWidgets.QVBoxLayout()
        state_box.addWidget(_label("ESTADO INFORMADO PELO ROBÔ", "NoctTitle"))
        self.state = QtWidgets.QLabel("—")
        self.state.setObjectName("NoctState")
        state_box.addWidget(self.state)
        self.requested = _label("", "NoctValue")
        state_box.addWidget(self.requested)
        head.addLayout(state_box, 2)
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(18)
        self.values: dict[str, QtWidgets.QLabel] = {}
        names = (("cal", "calibração"), ("cross", "cruzamentos"), ("lap", "tempo da volta"), ("err", "erro"),
                 ("corr", "correção PD"), ("pwm", "PWM esq. / dir."), ("b", "velocidade alvo"),
                 ("gains", "Kp / Kd"), ("policy", "sem link o firmware"), ("fail", "última falha"))
        for i, (key, title) in enumerate(names):
            grid.addWidget(_label(title.upper(), "NoctDim"), (i // 2) * 2, i % 2)
            value = _label("—", "NoctValue")
            grid.addWidget(value, (i // 2) * 2 + 1, i % 2)
            self.values[key] = value
        head.addLayout(grid, 3)
        main.addLayout(head)
        self.bars = SensorBars()
        main.addWidget(self.bars)
        self.graph = TelemetryGraph()
        main.addWidget(self.graph, 1)
        root.addLayout(main, 1)
        side = QtWidgets.QFrame()
        side.setObjectName("NoctSide")
        side.setFixedWidth(400)
        lay = QtWidgets.QVBoxLayout(side)
        lay.setContentsMargins(14, 4, 14, 4)
        lay.setSpacing(6)
        self.stop_button = QtWidgets.QPushButton("PARADA DE EMERGÊNCIA  (F12)")
        self.stop_button.setObjectName("NoctStop")
        self.stop_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self.emergency_stop)
        lay.addWidget(self.stop_button)
        lay.addWidget(_label("A parada pelo Bluetooth NÃO substitui o botão físico que corta a alimentação dos "
                             "motores.", "NoctDim"))
        self.feedback = _label("", "NoctValue")
        lay.addWidget(self.feedback)
        scroll = QtWidgets.QScrollArea()                    # a PARADA fica fixa; o resto rola se faltar altura
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        body = QtWidgets.QWidget()
        body.setObjectName("Panel")
        scroll.setWidget(body)
        scroll.viewport().setAutoFillBackground(False)
        lay.addWidget(scroll, 1)
        lay = QtWidgets.QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(6)
        link = QtWidgets.QHBoxLayout()
        self.connect_button = _button("CONECTAR", "Conecta ao robô configurado em CONFIGURAÇÕES > NOCTÁRIO",
                                      primary=True)
        self.connect_button.clicked.connect(lambda: self._skill("connect", "noctario.connect"))
        self.disconnect_button = _button("DESCONECTAR", "Sem link, vale a política do firmware")
        self.disconnect_button.clicked.connect(lambda: self._skill("disconnect", "noctario.disconnect"))
        link.addWidget(self.connect_button)
        link.addWidget(self.disconnect_button)
        lay.addLayout(link)
        motion = QtWidgets.QGridLayout()
        self.motion_buttons = []
        for i, (text, skill, args, tip) in enumerate((
                ("PARTIDA", "noctario.start", {}, "Dar a partida (o JARVIS pede confirmação: o robô vai se mover)"),
                ("PARAR", "noctario.stop", {}, "Parada com a rampa de frenagem"),
                ("CALIBRAR", "noctario.calibrate", {}, "3 s: passe a barra de sensores sobre a linha e o fundo"),
                ("CALIBRAR GIRANDO", "noctario.calibrate", {"auto": True}, "O robô gira no lugar (pede confirmação)"),
                ("LIBERAR EMERGÊNCIA", "noctario.clear", {}, "Sai da parada de emergência (fica parado)"),
                ("ZERAR CRUZAMENTOS", "noctario.reset_crossings", {}, "Zera a contagem do robô"),
                ("MOTOR ESQUERDO", "noctario.motor_test", {"l": 120, "r": 0, "ms": 500},
                 "Bancada, rodas fora do chão: 0,5 s para a frente. Girou para trás? 'Sentido do motor esquerdo'"),
                ("MOTOR DIREITO", "noctario.motor_test", {"l": 0, "r": 120, "ms": 500},
                 "Bancada, rodas fora do chão: 0,5 s para a frente. Girou para trás? 'Sentido do motor direito'"))):
            button = _button(text, tip, primary=text == "PARTIDA")
            button.clicked.connect(lambda _=False, s=skill, a=args: self._skill(s, s, a))
            motion.addWidget(button, i // 2, i % 2)
            self.motion_buttons.append(button)
        lay.addLayout(motion)
        lay.addWidget(_label("PARÂMETROS (limites do protocolo)", "NoctTitle"))
        form = QtWidgets.QFormLayout()
        form.setVerticalSpacing(3)
        for key in SETTINGS_KEYS:
            spec = PARAMS[key]
            if spec.choices:
                field = QtWidgets.QComboBox()
                for choice in spec.choices:
                    field.addItem(CHOICE_LABELS.get((key, choice), str(choice)), choice)
            elif spec.kind == "float":
                field = QtWidgets.QDoubleSpinBox()
                field.setDecimals(4)
                field.setRange(spec.low, spec.high)
                field.setSingleStep(0.001 if spec.high <= 0.5 else 0.01)
            else:
                field = QtWidgets.QSpinBox()
                field.setRange(int(spec.low), int(spec.high))
            field.setToolTip(spec.help if spec.choices else f"{spec.help} — limite {fmt(spec.low)} a {fmt(spec.high)}")
            field.setMinimumHeight(26)
            form.addRow(_label(spec.label + (f" ({spec.unit})" if spec.unit else ""), "NoctDim"), field)
            self._fields[key] = field
        lay.addLayout(form)
        params = QtWidgets.QHBoxLayout()
        self.apply_button = _button("APLICAR", "Envia só o que mudou (o JARVIS pede confirmação)", primary=True)
        self.apply_button.clicked.connect(self.apply_params)
        self.reload_button = _button("RELER", "Lê os parâmetros do robô")
        self.reload_button.clicked.connect(lambda: self._skill("params", "noctario.params"))
        self.save_button = _button("SALVAR NO ROBÔ", "Grava na memória do robô")
        self.save_button.clicked.connect(lambda: self._skill("save", "noctario.save_params"))
        for button in (self.apply_button, self.reload_button, self.save_button):
            params.addWidget(button)
        lay.addLayout(params)
        history_head = QtWidgets.QHBoxLayout()
        history_head.addWidget(_label("VOLTAS GRAVADAS", "NoctTitle"), 1)
        self.analyze_button = _button("ANALISAR NA TARDIS", "Telemetria da volta escolhida (ou das últimas)")
        self.analyze_button.clicked.connect(self.analyze)
        history_head.addWidget(self.analyze_button)
        lay.addLayout(history_head)
        self.history = QtWidgets.QListWidget()
        self.history.setMinimumHeight(130)
        lay.addWidget(self.history)
        lay.addWidget(_label("ALERTAS", "NoctTitle"))
        self.alerts = QtWidgets.QListWidget()
        self.alerts.setMinimumHeight(100)
        lay.addWidget(self.alerts)
        lay.addStretch(1)
        root.addWidget(side)

    # ------------------------------------------------------------ ações
    def emergency_stop(self) -> dict:
        """Imediato: sem confirmação, sem fila, sem passar pelo modelo."""
        outcome = self.service.estop(origin="interface")
        self.feedback.setText("PARADA DE EMERGÊNCIA enviada." if outcome["sent"] else
                              f"PARADA NÃO enviada: {outcome['detail']}")
        self.refresh()
        return outcome

    def _skill(self, key: str, skill: str, args: dict | None = None) -> None:
        self.feedback.setText(f"{skill.split('.')[-1]}: pedido enviado ao JARVIS…")
        self.runner.run(key, self.core.run_skill, skill, dict(args or {}), origin="user")

    def apply_params(self) -> None:
        current = self.service.params
        changed = {}
        for key, field in self._fields.items():
            value = field.currentData() if isinstance(field, QtWidgets.QComboBox) else field.value()
            if isinstance(field, QtWidgets.QDoubleSpinBox):
                value = round(float(value), 4)
            if current.get(key) != value:
                changed[key] = value
        if not changed:
            self.feedback.setText("Nenhum parâmetro mudou.")
            return
        self._skill("set", "noctario.set_params", changed)

    def analyze(self) -> None:
        engine = getattr(self.core, "tardis", None)
        if engine is None:
            self.feedback.setText("A TARDIS não está ativa nesta execução.")
            return
        item = self.history.currentItem()
        data = {"run": item.data(QtCore.Qt.UserRole)} if item is not None else {}
        self.runner.run("analyze", engine.submit, "telemetria", data, origin="usuario")

    @QtCore.Slot(str, object)
    def _done(self, key: str, value) -> None:
        if key == "runs":
            self._runs = [] if isinstance(value, Exception) else list(value or [])
            self.history.clear()
            for run in self._runs:
                when = time.strftime("%d/%m %H:%M", time.localtime(run["started"]))
                duration = f"{run['duration_s']:.1f} s" if run.get("duration_s") else "—"
                tag = "SIM · " if run["source"] == "simulador" else ""
                item = QtWidgets.QListWidgetItem(f"{when}  {tag}{RESULT_LABELS.get(run['result'], run['result'])}  "
                                                 f"{duration}  {len(run.get('crossings') or [])} cruz.")
                item.setData(QtCore.Qt.UserRole, run["id"])
                self.history.addItem(item)
            return
        if key == "analyze":
            if isinstance(value, Exception):
                self.feedback.setText(f"A TARDIS não aceitou: {value}")
            else:
                self.feedback.setText(f"Análise enviada à TARDIS ({value.state.lower()}): veja na sala de controle, "
                                      f"painel TELEMETRIA.")
            return
        if isinstance(value, Exception):
            self.feedback.setText(f"Falhou: {value}")
        elif isinstance(value, dict):
            text = value.get("text") or value.get("error") or value.get("status")
            if value.get("status") == "denied":
                text = "Negado: nada foi enviado ao robô."
            self.feedback.setText(str(text))
        if key in ("params", "set", "connect"):
            self._loaded_params = {}
        self.refresh()

    # ------------------------------------------------------------ leitura
    def refresh(self) -> None:
        status = self.service.status()
        connected = status["link"] == "conectado"
        if status["simulated"] and connected:
            self.banner.setText("SIMULADOR — não é o robô. Tudo nesta página vem de um modelo de teste.")
            self.banner.setStyleSheet("background: rgba(255, 179, 71, 50); color: #FFD9A0;")
        elif connected:
            self.banner.setText(f"CONECTADO · {status['transport']} · firmware {status['fw'] or '?'}")
            self.banner.setStyleSheet("background: rgba(61, 255, 168, 30); color: #A8FFD9;")
        else:
            self.banner.setText(f"SEM CONEXÃO — nenhum dado do robô ({status['link_label']}"
                                + (f": {status['detail']}" if status["detail"] else "") + ")")
            self.banner.setStyleSheet("background: rgba(255, 93, 115, 30); color: #FFB3BF;")
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(status["link"] != "desconectado")
        for button in self.motion_buttons + [self.apply_button, self.reload_button, self.save_button]:
            button.setEnabled(connected)
        requested = status["requested"]
        self.state.setText(status["state_label"].upper() if connected else "—")
        if requested.get("label") and connected:
            self.requested.setText(f"pedido: {requested['label']} — {requested['status']} (há {requested['age']:.1f} s)")
        else:
            self.requested.setText("")
        tel = self.service.telemetry if connected else {}
        params = status["params"] if connected else {}
        v = self.values
        v["cal"].setText(("sim" if status["cal"] else "NÃO") if connected else "—")
        v["cross"].setText(f"{status['crossings']} de {status['target']}" if connected else "—")
        v["lap"].setText(f"{status['lap_ms'] / 1000:.1f} s" if connected and status["lap_ms"] else "—")
        v["err"].setText(str(tel.get("err")) if tel.get("err") is not None else "—")
        v["corr"].setText(f"{tel['corr']:.2f}" if tel.get("corr") is not None else "—")
        v["pwm"].setText(f"{tel.get('l')} / {tel.get('r')}" if tel.get("l") is not None else "—")
        v["b"].setText(str(tel.get("b")) if tel.get("b") is not None else "—")
        v["gains"].setText(f"{fmt(params.get('kp'))} / {fmt(params.get('kd'))}" if params else "—")
        v["policy"].setText({"stop": "PARA", "continue": "TERMINA O PERCURSO"}.get(status["policy"], "—")
                            if connected else "—")
        v["fail"].setText(status["last_failure"] or "nenhuma")
        if connected and params and params != self._loaded_params:
            self._loaded_params = dict(params)
            for key, field in self._fields.items():
                if key not in params:
                    continue
                if isinstance(field, QtWidgets.QComboBox):
                    field.setCurrentIndex(max(0, field.findData(params[key])))
                else:
                    field.setValue(params[key])
        if connected and tel:
            self.bars.set_reading(tel.get("s") or [], tel.get("pos"), bool(tel.get("lost")))
            self.graph.set_samples(self.service.recent_series(self.graph.window))
        else:
            self.bars.set_reading([], None, False)
            self.graph.set_samples([], "SEM CONEXÃO — nenhum dado do robô" if not connected else
                                   "conectado, sem telemetria (TEL desligada no robô?)")
        alerts = self.service.recent_alerts(10)
        if self.alerts.count() != len(alerts):
            self.alerts.clear()
            for alert in alerts:
                when = time.strftime("%H:%M:%S", time.localtime(alert["at"]))
                item = QtWidgets.QListWidgetItem(f"{when}  {alert['text']}")
                item.setForeground(QtGui.QColor("#FF5D73" if alert["severity"] == "alta" else "#FFB347"))
                self.alerts.addItem(item)
        self.frames += 1
        self._schedule(connected)

    def _schedule(self, connected: bool) -> None:
        if not self.isVisible():
            self._timer.stop()
            return
        interval = 50 if connected else 500                  # ≤ 20 quadros/s com o robô; 2/s sem ele
        if self._timer.interval() != interval or not self._timer.isActive():
            self._timer.start(interval)

    def platform_event(self, kind: str, payload: dict, at: float | None = None) -> None:
        if kind == "NOCTARIO_RUN":
            self.load_runs()
        if kind.startswith("NOCTARIO_") and self.isVisible():
            self.refresh()

    def load_runs(self) -> None:
        self.runner.run("runs", lambda: [{k: v for k, v in r.items() if k != "samples"}
                                         for r in self.service.store.runs(30, samples=False)]
                        if self.service.store is not None else [])

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self.load_runs()
        self.refresh()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._timer.stop()
        super().hideEvent(event)

    def shutdown(self) -> None:
        self._timer.stop()
