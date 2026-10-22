"""CONFIGURAÇÕES — tudo o que o usuário pode ajustar, num só lugar.

Cada controle grava pela ``SettingsManager`` (validação, arquivo e avisos aos módulos); se um valor
for recusado pela validação, o controle volta ao valor efetivo e a página diz por quê. Escolhas que
mudam o que sai do computador (OpenAI, modo padrão de privacidade, modelos externos) pedem
confirmação explícita com o que muda. A chave da OpenAI vai para o cofre do sistema e nunca é
exibida inteira. "Iniciar com o Windows" altera o Registro só por clique do usuário e mostra o estado
real lido de volta. "Restaurar padrões" guarda uma cópia do arquivo antes e mantém microfone, saída
de áudio, calibração da voz, endereço do Noctário e fuso.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ..agent.permissions import DEFAULT_POLICY, FLOORS, LABELS, MODE_LABELS, parse_policy, policy_entries
from ..config.settings import PERMISSION_CATEGORIES, PERMISSION_MODES, START_PAGES
from ..platform import autostart, credentials
from . import quality, theme
from .panels import _button, _label

SECTIONS = (("geral", "GERAL E INÍCIO"), ("voz", "VOZ E ÁUDIO"), ("ia", "INTELIGÊNCIA"),
            ("privacidade", "PRIVACIDADE E OBSERVADOR"), ("permissoes", "PERMISSÕES"),
            ("aparencia", "APARÊNCIA E DESEMPENHO"), ("noctario", "NOCTÁRIO"), ("registros", "HISTÓRICO E REGISTROS"),
            ("restaurar", "RESTAURAR PADRÕES"))
PAGE_LABELS = {"jarvis": "JARVIS", "tardis": "TARDIS", "noctario": "NOCTÁRIO", "atividades": "ATIVIDADES",
               "configuracoes": "CONFIGURAÇÕES", "diagnosticos": "DIAGNÓSTICOS"}


class SettingsPage(QtWidgets.QWidget):
    _devices_ready = QtCore.Signal(str, object)       # ("input"|"output", resultado da listagem)
    _message = QtCore.Signal(str)

    def __init__(self, core, parent=None, *, ask: Callable[..., bool] | None = None):
        super().__init__(parent)
        self.core = core
        self.setObjectName("Panel")
        self.setStyleSheet(theme.PANEL_STYLESHEET + """
            QWidget#SettingsForm { background: #071426; }
            QDoubleSpinBox { background: #050E1C; color: #DCEEFF; border: 1px solid rgba(0, 217, 255, 60);
                border-radius: 4px; padding: 5px 8px; }
            QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { min-height: 22px; }
            QListWidget#H2Nav::item { background: transparent; padding: 11px 16px; }
            QListWidget#H2Nav::item:selected { background: rgba(0, 217, 255, 30); color: #E6FBFF;
                border-left: 2px solid #00D9FF; }
        """)
        self._ask = ask or self._confirm_dialog
        self._refreshers: list[Callable[[], None]] = []
        self._loading = False
        self._devices_ready.connect(self._show_devices, QtCore.Qt.QueuedConnection)
        self._message.connect(self._say, QtCore.Qt.QueuedConnection)
        self.nav = QtWidgets.QListWidget()
        self.nav.setObjectName("H2Nav")
        self.nav.setFixedWidth(250)
        self.stack = QtWidgets.QStackedWidget()
        self.forms: dict[str, QtWidgets.QFormLayout] = {}
        builders = {"geral": self._build_general, "voz": self._build_voice, "ia": self._build_ai,
                    "privacidade": self._build_privacy, "permissoes": self._build_permissions,
                    "aparencia": self._build_appearance, "noctario": self._build_noctario,
                    "registros": self._build_records, "restaurar": self._build_reset}
        for key, label in SECTIONS:
            self.nav.addItem(label)
            form_host = QtWidgets.QWidget()
            form_host.setObjectName("SettingsForm")
            form_host.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            form_host.setMaximumWidth(1100)                    # campos legíveis, sem esticar a tela toda
            form = QtWidgets.QFormLayout(form_host)
            form.setContentsMargins(26, 18, 26, 18)
            form.setHorizontalSpacing(18)
            form.setVerticalSpacing(12)
            form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            form.addRow(_label(label, "PanelTitle"))
            self.forms[key] = form
            builders[key](form)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
            scroll.setWidget(form_host)
            viewport = scroll.viewport()                       # sem o cinza do sistema ao lado do formulário
            palette = viewport.palette()
            palette.setColor(QtGui.QPalette.Window, theme.BG2)
            viewport.setPalette(palette)
            viewport.setAutoFillBackground(True)
            self.stack.addWidget(scroll)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.status = _label("", "PanelDim")
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.addLayout(body, 1)
        self.status.setContentsMargins(22, 0, 22, 0)
        root.addWidget(self.status)
        self.refresh()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), theme.BG2)
        p.end()

    # ------------------------------------------------------------ base
    @property
    def settings(self):
        return self.core.settings()

    def show_section(self, key: str) -> None:
        keys = [k for k, _ in SECTIONS]
        if key in keys:
            self.nav.setCurrentRow(keys.index(key))

    def _say(self, text: str) -> None:
        self.status.setText(text)

    def apply(self, **values: Any) -> bool:
        """Grava pela SettingsManager; devolve False (e explica) se algum valor foi recusado."""
        if self._loading:
            return True
        try:
            self.core.settings_manager.update(**values)
        except Exception as exc:
            self._say(f"Não foi possível gravar: {exc}")
            self.refresh()
            return False
        refused = [k for k, v in values.items() if _norm(getattr(self.settings, k, None)) != _norm(v)]
        if refused:
            self._say(f"Valor recusado pela validação: {', '.join(refused)}. O valor efetivo foi mantido.")
            self.refresh()
            return False
        self._say("Configuração gravada.")
        return True

    def refresh(self) -> None:
        """Relê todos os controles das configurações efetivas (após restaurar, voz, outro painel...)."""
        self._loading = True
        try:
            for refresher in self._refreshers:
                try:
                    refresher()
                except Exception:
                    pass
        finally:
            self._loading = False

    def on_settings_changed(self, changed: list) -> None:
        if self.isVisible():
            self.refresh()

    def _confirm_dialog(self, title: str, text: str) -> bool:
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setText(text)
        box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        box.setDefaultButton(QtWidgets.QMessageBox.No)
        box.button(QtWidgets.QMessageBox.Yes).setText("Confirmo")
        box.button(QtWidgets.QMessageBox.No).setText("Cancelar")
        return box.exec() == QtWidgets.QMessageBox.Yes

    # ------------------------------------------------------------ controles ligados a campos
    def check(self, form, field: str, text: str, tip: str = "", *,
              on_change: Callable[[bool], None] | None = None) -> QtWidgets.QCheckBox:
        box = QtWidgets.QCheckBox(text)
        box.setToolTip(tip)
        box.toggled.connect(lambda on: (on_change or (lambda v: self.apply(**{field: v})))(bool(on)))
        self._refreshers.append(lambda: _set_checked(box, bool(getattr(self.settings, field))))
        form.addRow("", box)
        return box

    def combo(self, form, field: str, label: str, items: list[tuple[str, str]], tip: str = "", *,
              on_change: Callable[[str], None] | None = None) -> QtWidgets.QComboBox:
        widget = QtWidgets.QComboBox()
        widget.setToolTip(tip)
        for value, text in items:
            widget.addItem(text, value)
        widget.activated.connect(lambda index: (on_change or (lambda v: self.apply(**{field: v})))(
            widget.itemData(index)))
        self._refreshers.append(lambda: _set_combo(widget, getattr(self.settings, field)))
        form.addRow(label, widget)
        return widget

    def number(self, form, field: str, label: str, low: float, high: float, *, step: float = 1, decimals: int = 0,
               suffix: str = "", tip: str = "") -> QtWidgets.QAbstractSpinBox:
        if decimals:
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(decimals)
        else:
            widget = QtWidgets.QSpinBox()
        widget.setRange(low, high)
        widget.setSingleStep(step)
        widget.setSuffix(suffix)
        widget.setToolTip(tip)
        widget.setKeyboardTracking(False)
        widget.valueChanged.connect(lambda value: self.apply(**{field: value}))
        self._refreshers.append(lambda: _set_value(widget, getattr(self.settings, field)))
        form.addRow(label, widget)
        return widget

    def line(self, form, field: str, label: str, *, placeholder: str = "", tip: str = "",
             as_list: bool = False) -> QtWidgets.QLineEdit:
        widget = QtWidgets.QLineEdit()
        widget.setPlaceholderText(placeholder)
        widget.setToolTip(tip)

        def commit() -> None:
            text = widget.text().strip()
            value = [x.strip() for x in text.split(",") if x.strip()] if as_list else text
            current = getattr(self.settings, field)
            if _norm(current) != _norm(value):
                self.apply(**{field: value})

        widget.editingFinished.connect(commit)
        self._refreshers.append(lambda: widget.setText(", ".join(getattr(self.settings, field)) if as_list
                                                       else str(getattr(self.settings, field))))
        form.addRow(label, widget)
        return widget

    # ------------------------------------------------------------ GERAL E INÍCIO
    def _build_general(self, form) -> None:
        self.combo(form, "start_page", "Página ao abrir", [(k, PAGE_LABELS.get(k, k)) for k in START_PAGES],
                   "Página mostrada quando o JARVIS abre")
        self.check(form, "hud_start_minimized", "Iniciar recolhido no orbe (só o orbe na tela)")
        self.check(form, "hud_auto_expand", "Expandir sozinho ao ouvir \"Jarvis\" ou quando houver autorização "
                                            "pendente")
        self.autostart_state = _label("", "PanelDim")
        self.autostart_box = QtWidgets.QCheckBox("Iniciar com o Windows")
        self.autostart_box.setToolTip("Grava (ou remove) a entrada \"JARVIS\" em HKCU\\...\\Run — só quando você "
                                      "clica aqui")
        self.autostart_box.clicked.connect(self._toggle_autostart)
        form.addRow("", self.autostart_box)
        form.addRow("", self.autostart_state)
        self._refreshers.append(self._refresh_autostart)
        self.check(form, "privacy_shield_on_start", "Abrir já em modo privacidade (microfone fechado)")
        self.check(form, "observer_restore_on_start", "Ao iniciar, voltar ao último modo do Observador (desligado: "
                                                      "começa sempre DESLIGADO, como no original)")

    def _refresh_autostart(self) -> None:
        info = autostart.check()
        _set_checked(self.autostart_box, info["status"] in ("OK", "STALE", "LEGACY"))
        self.autostart_box.setEnabled(info["status"] != "UNAVAILABLE")
        self.autostart_state.setText(info["text"])

    def _toggle_autostart(self, on: bool) -> None:
        if not autostart.supported():
            self._say("Início automático: disponível apenas no Windows.")
            self._refresh_autostart()
            return
        try:
            (autostart.enable if on else autostart.disable)()
            self.core.settings_manager.update(startup=bool(on))
        except OSError as exc:
            self._say(f"O Registro recusou a alteração: {exc}")
        self._refresh_autostart()                          # sempre o estado REAL lido de volta

    # ------------------------------------------------------------ VOZ E ÁUDIO
    def _build_voice(self, form) -> None:
        self.check(form, "voice_enabled", "Voz do JARVIS (microfone e fala)")
        self.combo(form, "voice_profile", "Timbre", [("jarvis", "JARVIS — masculina, grave, natural"),
                                                     ("neutral", "Neutro")])
        self.number(form, "volume", "Volume da fala", 0.0, 1.0, step=0.05, decimals=2)
        self.number(form, "speech_speed", "Velocidade da fala", 0.6, 1.4, step=0.05, decimals=2,
                    tip="1,00 = normal; menor = mais devagar")
        self.check(form, "captions", "Legendas sincronizadas com a fala")
        self.line(form, "wake_words", "Palavras de ativação", as_list=True, placeholder="jarvis",
                  tip="Separadas por vírgula")
        self.mic_list = QtWidgets.QComboBox()
        self.mic_list.setMinimumWidth(320)
        mic_row = QtWidgets.QHBoxLayout()
        mic_row.addWidget(self.mic_list, 1)
        refresh_mics = _button("LISTAR", "Ler os microfones disponíveis (nada é aberto)")
        refresh_mics.clicked.connect(lambda: self.load_devices("input"))
        use_mic = _button("USAR ESTE", "Trocar o microfone do JARVIS e reabrir a captura", primary=True)
        use_mic.clicked.connect(self._use_mic)
        mic_row.addWidget(refresh_mics)
        mic_row.addWidget(use_mic)
        form.addRow("Microfone", mic_row)
        self.mic_state = _label("", "PanelDim")
        form.addRow("", self.mic_state)
        self._refreshers.append(lambda: self.mic_state.setText(
            f"Configurado: {self.settings.mic_name or 'padrão do sistema'}"
            + (f" (índice {self.settings.mic_index})" if self.settings.mic_index >= 0 else "")))
        self.out_list = QtWidgets.QComboBox()
        self.out_list.setMinimumWidth(320)
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(self.out_list, 1)
        refresh_out = _button("LISTAR", "Ler as saídas de áudio disponíveis (nada é aberto)")
        refresh_out.clicked.connect(lambda: self.load_devices("output"))
        use_out = _button("USAR ESTA", "Trocar a saída de áudio (a fala em andamento é interrompida)", primary=True)
        use_out.clicked.connect(self._use_output)
        out_row.addWidget(refresh_out)
        out_row.addWidget(use_out)
        form.addRow("Saída de áudio", out_row)
        self.out_state = _label("", "PanelDim")
        form.addRow("", self.out_state)
        self._refreshers.append(self._refresh_output_state)
        self.check(form, "sound_effects", "Efeitos sonoros da interface")
        self.number(form, "sfx_volume", "Volume dos efeitos", 0.0, 1.0, step=0.05, decimals=2)

    def _refresh_output_state(self) -> None:
        out = getattr(self.core, "audio_out", None)
        chosen = self.settings.audio_output_name or ("índice " + str(self.settings.audio_output_index)
                                                     if self.settings.audio_output_index >= 0 else "padrão do sistema")
        opened = getattr(out, "device", "") or "—"
        self.out_state.setText(f"Configurada: {chosen} · aberta agora: {opened} ({getattr(out, 'backend', '—')})")

    def load_devices(self, kind: str) -> None:
        self._say("Lendo dispositivos de áudio…")

        def work():
            from ..voice import audio
            try:
                result = audio.list_input_devices() if kind == "input" else audio.list_output_devices()
            except Exception as exc:
                result = {"devices": [], "errors": [str(exc)]}
            self._devices_ready.emit(kind, result)

        threading.Thread(target=work, name="ultron-settings-devices", daemon=True).start()

    def _show_devices(self, kind: str, result: dict) -> None:
        target = self.mic_list if kind == "input" else self.out_list
        target.clear()
        target.addItem("Padrão do sistema", {"name": "", "index": -1})
        for device in result.get("devices", []):
            label = f"{device['name']} ({device.get('host_api', '')})" + (" — padrão" if device.get("default") else "")
            target.addItem(label, {"name": device["name"], "index": device["index"]})
        errors = "; ".join(result.get("errors") or [])
        self._say(f"{len(result.get('devices', []))} dispositivo(s) encontrado(s)." + (f" Avisos: {errors}"
                                                                                       if errors else ""))

    def _use_mic(self) -> None:
        data = self.mic_list.currentData()
        if data is None:
            self._say("Clique em LISTAR e escolha um microfone.")
            return
        if not getattr(self.core, "enable_voice", False):
            self.apply(mic_name=data["name"], mic_index=data["index"])
            return
        manager = self.core.settings_manager

        def work():
            try:
                self.core.voice.select_device(data["name"], data["index"], settings_manager=manager)
                self._message.emit(f"Microfone: {data['name'] or 'padrão do sistema'}. A captura foi reaberta.")
            except Exception as exc:
                self._message.emit(f"Não foi possível trocar o microfone: {exc}")

        threading.Thread(target=work, name="ultron-settings-mic", daemon=True).start()

    def _use_output(self) -> None:
        data = self.out_list.currentData()
        if data is None:
            self._say("Clique em LISTAR e escolha uma saída.")
            return
        if self.apply(audio_output_name=data["name"], audio_output_index=data["index"]):
            self._say(f"Saída de áudio: {data['name'] or 'padrão do sistema'} (reaberta em segundo plano).")
            QtCore.QTimer.singleShot(1500, self._refresh_output_state)

    # ------------------------------------------------------------ INTELIGÊNCIA
    def _build_ai(self, form) -> None:
        self.provider = self.combo(form, "ai_provider", "Cérebro", [("ollama", "Ollama local (nada sai do computador)"),
                                                                    ("openai", "OpenAI (pela internet, com sua chave)")],
                                   on_change=self._choose_provider)
        self.provider_state = _label("", "PanelDim")
        form.addRow("", self.provider_state)
        self._refreshers.append(self._refresh_provider)
        self.line(form, "model", "Modelo Ollama (texto)", placeholder="qwen2.5:3b")
        self.line(form, "vision_model", "Modelo Ollama (visão)", placeholder="qwen2.5vl:3b")
        self.line(form, "ollama_url", "Endereço do Ollama", placeholder="http://127.0.0.1:11434")
        self.line(form, "openai_model", "Modelo da OpenAI", placeholder="gpt-5.6-sol")
        self.check(form, "openai_web_search", "Pesquisa web da OpenAI (quando a OpenAI é o cérebro)")
        key_row = QtWidgets.QHBoxLayout()
        self.key_state = _label("", "PanelDim")
        save_key = _button("GRAVAR CHAVE…", "Guardar a chave no cofre do sistema (Gerenciador de Credenciais)")
        save_key.clicked.connect(self._save_key)
        remove_key = _button("REMOVER CHAVE", "Apagar a chave do cofre do sistema")
        remove_key.clicked.connect(self._remove_key)
        test = _button("TESTAR", "Uma chamada mínima à OpenAI para conferir chave, modelo e rede")
        test.clicked.connect(self._test_openai)
        key_row.addWidget(self.key_state, 1)
        key_row.addWidget(save_key)
        key_row.addWidget(remove_key)
        key_row.addWidget(test)
        form.addRow("Chave da OpenAI", key_row)
        self._refreshers.append(self._refresh_key)

    def _refresh_provider(self) -> None:
        openai = getattr(self.core, "openai", None)
        if self.settings.ai_provider == "openai" and openai is not None:
            blocked = openai.blocked_reason()
            self.provider_state.setText("OpenAI em uso." if not blocked else
                                        f"OpenAI escolhida, mas bloqueada: {blocked}. O Ollama local responde.")
        else:
            self.provider_state.setText("Ollama local: nenhuma chamada de IA sai do computador.")

    def _refresh_key(self) -> None:
        source = credentials.source("openai_api_key")
        value = credentials.get_secret("openai_api_key") if source else ""
        self.key_state.setText(f"{credentials.mask(value)} (de: {source})" if source else "ausente")

    def _choose_provider(self, value: str) -> None:
        if value == "openai" and self.settings.ai_provider != "openai":
            consent = self._ask("Usar a OpenAI como cérebro",
                                "Os pedidos, o contexto da conversa e as imagens que você pedir para analisar serão "
                                "enviados à OpenAI pela internet (cobrança na sua conta). As ferramentas continuam "
                                "rodando no seu computador, com as mesmas permissões e confirmações.\n\n"
                                "Isto muda o modo de privacidade para PADRÃO e permite modelos externos. Se a OpenAI "
                                "falhar, o Ollama local responde.\n\nConfirma?")
            if not consent:
                self.refresh()
                self._say("Nada mudou: o Ollama local continua como cérebro.")
                return
            self.apply(ai_provider="openai", privacy_mode="standard", allow_external_models=True)
        elif value == "ollama":
            self.apply(ai_provider="ollama")
        self._refresh_provider()

    def _save_key(self) -> None:
        key, ok = QtWidgets.QInputDialog.getText(self, "Chave da OpenAI", "Cole a chave (fica no cofre do sistema; "
                                                 "nunca em arquivo):", QtWidgets.QLineEdit.Password)
        if not ok or not key.strip():
            return
        try:
            where = credentials.set_secret("openai_api_key", key.strip())
            self._say(f"Chave gravada no {where}: {credentials.mask(key.strip())}.")
        except (RuntimeError, ValueError, OSError) as exc:
            self._say(f"A chave não foi gravada: {exc}")
        self._refresh_key()
        self._refresh_provider()

    def _remove_key(self) -> None:
        removed = credentials.delete_secret("openai_api_key")
        env = credentials.source("openai_api_key") == "ambiente"
        self._say(("Chave removida do cofre." if removed else "Não havia chave no cofre.")
                  + (" A variável de ambiente OPENAI_API_KEY continua definida." if env else ""))
        self._refresh_key()
        self._refresh_provider()

    def _test_openai(self) -> None:
        openai = getattr(self.core, "openai", None)
        if openai is None:
            self._say("Provedor OpenAI indisponível nesta execução.")
            return
        blocked = openai.blocked_reason()
        if blocked:
            self._say(f"Teste não enviado: {blocked}.")
            return
        self._say("Testando a OpenAI…")

        def work():
            try:
                result = openai.chat([{"role": "user", "content": "Responda apenas: ok"}], timeout=25.0)
                self._message.emit(f"OpenAI respondeu ({result.model}): {result.content[:60] or '(vazio)'}")
            except Exception as exc:
                kind = getattr(exc, "kind", type(exc).__name__)
                self._message.emit(f"OpenAI falhou [{kind}]: {exc}")

        threading.Thread(target=work, name="ultron-settings-openai", daemon=True).start()

    # ------------------------------------------------------------ PRIVACIDADE E OBSERVADOR
    def _build_privacy(self, form) -> None:
        self.combo(form, "privacy_mode", "Modo de privacidade",
                   [("local", "LOCAL — nada sai do computador"),
                    ("standard", "PADRÃO — serviços externos só com permissão explícita")],
                   on_change=self._choose_privacy)
        self.check(form, "allow_external_models", "Permitir modelos de IA externos (exige o modo PADRÃO)",
                   on_change=self._choose_external)
        self.observer = self.combo(form, "observer_mode", "Observador da tela",
                                   [("off", "Desligado"), ("assistant", "Assistente — sugere na tela"),
                                    ("observer", "Observador — sugere e fala")], on_change=self._choose_observer)
        self.number(form, "vision_interval", "Intervalo da análise visual", 5, 3600, step=5, decimals=0,
                    suffix=" s")
        self.excluded = QtWidgets.QListWidget()
        self.excluded.setMaximumHeight(140)
        self._refreshers.append(lambda: (self.excluded.clear(), self.excluded.addItems(list(self.settings.excluded_apps))))
        buttons = QtWidgets.QHBoxLayout()
        add = _button("ADICIONAR", "Programa que nunca é observado (ex.: banco, gerenciador de senhas)")
        add.clicked.connect(self._add_excluded)
        remove = _button("REMOVER")
        remove.clicked.connect(self._remove_excluded)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        box = QtWidgets.QVBoxLayout()
        box.addWidget(self.excluded)
        box.addLayout(buttons)
        form.addRow("Apps sem monitoramento", box)
        self.check(form, "auto_capture", "Registrar sozinho tarefas e lembretes com intenção clara (reversível)")

    def _choose_privacy(self, value: str) -> None:
        if value == "standard" and self.settings.privacy_mode == "local":
            if not self._ask("Sair do LOCAL MODE", "No modo PADRÃO, serviços externos (OpenAI, pesquisa, testes de "
                                                   "conectividade) passam a ser possíveis — cada um ainda depende da "
                                                   "própria permissão. Confirma?"):
                self.refresh()
                return
        self.apply(privacy_mode=value)
        self._refresh_provider()

    def _choose_external(self, on: bool) -> None:
        if on and not self._ask("Modelos externos", "Permitir que um modelo de IA fora do computador (OpenAI) seja "
                                                    "usado quando escolhido como cérebro? Exige o modo PADRÃO."):
            self.refresh()
            return
        self.apply(allow_external_models=bool(on))
        self._refresh_provider()

    def _choose_observer(self, mode: str) -> None:
        action = {"off": "off", "assistant": "assistant", "observer": "observer"}.get(mode, "off")
        try:
            response = self.core.set_observer(action)
            self._say(response.text)
        except Exception as exc:
            self._say(f"Observador não alterado: {exc}")
        self.refresh()

    def _add_excluded(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "Apps sem monitoramento",
                                                  "Nome do programa (ex.: chrome.exe, KeePass):")
        name = name.strip()
        if ok and name:
            self.apply(excluded_apps=list(dict.fromkeys([*self.settings.excluded_apps, name])))
            self.refresh()

    def _remove_excluded(self) -> None:
        item = self.excluded.currentItem()
        if item is None:
            self._say("Selecione um programa da lista.")
            return
        self.apply(excluded_apps=[a for a in self.settings.excluded_apps if a != item.text()])
        self.refresh()

    # ------------------------------------------------------------ PERMISSÕES
    def _build_permissions(self, form) -> None:
        intro = _label("O que o JARVIS pode fazer por categoria. \"Permitir\" deixa a decisão com o risco de cada "
                       "ação (sensíveis continuam pedindo autorização); \"Confirmar sempre\" pergunta a cada vez; "
                       "\"Bloquear\" recusa. Apagar dados e comandos ao robô nunca ficam abaixo de \"Confirmar\". A "
                       "parada de emergência do robô nunca é bloqueada.", "PanelDim")
        form.addRow(intro)
        self.permission_boxes: dict[str, QtWidgets.QComboBox] = {}
        for category in PERMISSION_CATEGORIES:
            box = QtWidgets.QComboBox()
            floor = FLOORS.get(category, "permitir")
            for mode in PERMISSION_MODES:
                box.addItem(MODE_LABELS[mode], mode)
                if PERMISSION_MODES.index(mode) < PERMISSION_MODES.index(floor):
                    item = box.model().item(box.count() - 1)
                    item.setEnabled(False)                       # abaixo do piso: indisponível
            box.setToolTip(f"Padrão: {MODE_LABELS[DEFAULT_POLICY[category]]}"
                           + (f" · mínimo: {MODE_LABELS[floor]}" if category in FLOORS else ""))
            box.activated.connect(lambda _i, c=category: self._choose_permission(c))
            self.permission_boxes[category] = box
            label = LABELS[category]
            form.addRow(label[:1].upper() + label[1:], box)
        self._refreshers.append(self._refresh_permissions)
        self.combo(form, "autonomy_level", "Nível de autonomia",
                   [("restricted", "Restrita — pergunta antes de quase tudo"),
                    ("balanced", "Equilibrada — executa o que é comum e reversível"),
                    ("autonomous", "Autônoma — também tarefas moderadas e reversíveis")])
        self.number(form, "authorization_timeout", "Tempo para responder a uma autorização", 5, 300, step=5,
                    suffix=" s", tip="Sem resposta no prazo = NÃO")
        self.grants = _label("", "PanelDim")
        revoke = _button("REVOGAR AUTORIZAÇÕES PERMANENTES", "Toda ação volta a pedir confirmação")
        revoke.clicked.connect(self._revoke_all)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.grants, 1)
        row.addWidget(revoke)
        form.addRow("\"Sempre (24 h)\"", row)
        self._refreshers.append(lambda: self.grants.setText(
            f"{len(self.core.authorizations.standing())} autorização(ões) permanente(s) ativa(s)"))

    def _refresh_permissions(self) -> None:
        policy = parse_policy(self.settings.permission_policy)
        for category, box in self.permission_boxes.items():
            _set_combo(box, policy[category])

    def _choose_permission(self, category: str) -> None:
        policy = parse_policy(self.settings.permission_policy)
        policy[category] = self.permission_boxes[category].currentData()
        self.apply(permission_policy=list(policy_entries(policy)))
        self._refresh_permissions()

    def _revoke_all(self) -> None:
        count = self.core.authorizations.revoke(None)
        self._say(f"{count} autorização(ões) permanente(s) revogada(s).")
        self.refresh()

    # ------------------------------------------------------------ APARÊNCIA E DESEMPENHO
    def _build_appearance(self, form) -> None:
        self.combo(form, "performance_profile", "Perfil visual", [(n, quality.LABELS[n]) for n in quality.NAMES],
                   "Muda só o custo visual; execução, memória e segurança funcionam igual em todos")
        self.check(form, "heavy_effects", "Efeitos pesados (brilho, transições holográficas, varreduras)")
        self.combo(form, "avatar_mode", "Vista do JARVIS", [("face", "Rosto holográfico"),
                                                            ("neural", "Núcleo neural")])
        self.combo(form, "render_backend", "Renderização 3D", [("cpu", "CPU (funciona em qualquer máquina)"),
                                                               ("gpu", "GPU — OpenGL (volta para CPU se falhar)")])
        self.number(form, "hud_fps", "Quadros por segundo (máximo)", 15, 144, step=5)
        self.check(form, "ambient_sound", "Som ambiente discreto do TARDIS")

    # ------------------------------------------------------------ NOCTÁRIO
    def _build_noctario(self, form) -> None:
        form.addRow(_label("A interface envia comandos e lê telemetria; o controle PD roda no ESP32. Nenhuma partida "
                           "acontece sozinha. A parada por Bluetooth NÃO substitui um botão físico de parada no robô.",
                           "PanelDim"))
        self.combo(form, "noctario_transport", "Conexão", [("rfcomm", "Bluetooth direto (RFCOMM)"),
                                                           ("serial", "Porta COM do Bluetooth"),
                                                           ("simulator", "Simulador (rotulado como SIMULADO)")])
        self.line(form, "noctario_address", "Endereço Bluetooth", placeholder="AA:BB:CC:DD:EE:FF")
        self.number(form, "noctario_channel", "Canal RFCOMM", 1, 30)
        self.line(form, "noctario_port", "Porta COM", placeholder="COM5")
        self.check(form, "noctario_autoconnect", "Conectar ao iniciar (só conecta; nunca dá partida)")
        self.check(form, "noctario_reconnect", "Reconectar se o link cair (só reconecta; nunca dá partida)")
        self.number(form, "noctario_heartbeat_ms", "Batimento PC → robô", 0, 5000, step=50, suffix=" ms",
                    tip="0 = sem batimento; a política de desconexão é a do firmware")
        self.number(form, "noctario_telemetry_hz", "Telemetria pedida ao conectar", 1, 50, suffix=" Hz",
                    tip="só a taxa de envio; não é gravada no robô")

    # ------------------------------------------------------------ HISTÓRICO E REGISTROS
    def _build_records(self, form) -> None:
        self.check(form, "activity_history", "Registrar o histórico de atividades (pedidos, ações, confirmações)")
        self.number(form, "activity_keep", "Registros guardados", 100, 100000, step=500,
                    tip="Os mais antigos saem primeiro")
        self.check(form, "debug", "Registro detalhado no arquivo de log (vale ao reiniciar)")
        open_logs = _button("ABRIR PASTA DE LOGS")
        open_logs.clicked.connect(self._open_logs)
        form.addRow("", open_logs)

    def _open_logs(self) -> None:
        from ..config import paths
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(paths.logs_dir())))

    # ------------------------------------------------------------ RESTAURAR PADRÕES
    def _build_reset(self, form) -> None:
        form.addRow(_label("Volta todas as configurações ao padrão. Antes, uma cópia do arquivo atual é guardada "
                           "(settings.backup-AAAAMMDD-HHMMSS.json). São mantidos: microfone, saída de áudio, "
                           "calibração da voz, endereço do Noctário e fuso horário. Memórias, lembretes, histórico e "
                           "modelos não são tocados.", "PanelDim"))
        reset = _button("RESTAURAR PADRÕES", primary=True)
        reset.clicked.connect(self.reset_defaults)
        form.addRow("", reset)

    def reset_defaults(self) -> None:
        if not self._ask("Restaurar padrões", "Restaurar todas as configurações ao padrão? Uma cópia do arquivo atual "
                                              "será guardada antes."):
            return
        try:
            backup = self.core.settings_manager.reset_to_defaults()
        except Exception as exc:
            self._say(f"Não foi possível restaurar: {exc}")
            return
        self.refresh()
        self._say("Padrões restaurados." + (f" Cópia anterior: {backup}" if backup else ""))


# ====================================================================== utilidades
def _norm(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if isinstance(value, float):
        return round(value, 4)
    return value


def _set_checked(box: QtWidgets.QCheckBox, value: bool) -> None:
    box.blockSignals(True)
    box.setChecked(bool(value))
    box.blockSignals(False)


def _set_combo(box: QtWidgets.QComboBox, value: Any) -> None:
    index = box.findData(value)
    if index >= 0:
        box.blockSignals(True)
        box.setCurrentIndex(index)
        box.blockSignals(False)


def _set_value(widget: QtWidgets.QAbstractSpinBox, value: Any) -> None:
    widget.blockSignals(True)
    widget.setValue(value)
    widget.blockSignals(False)
