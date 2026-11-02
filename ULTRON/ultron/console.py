"""Modo console do JARVIS (``START_JARVIS.bat --console``).

O MESMO ``NeuralCore`` da interface gráfica — mesmo banco, configurações, memória pessoal e de projetos,
TARDIS, permissões, autorizações e executor —, só que conversando pelo terminal. Tudo o que é digitado entra
por ``core.submit`` como na barra de pedidos da janela: "sim"/"não" respondem às confirmações, "cancelar" ou
"pare" interrompem, e o resto vira pedido. A voz funciona quando disponível (diga "Jarvis"). Cada resposta é
esperada antes do próximo prompt, para a conversa não se misturar; avisos que chegam sozinhos (lembretes)
aparecem quando chegam.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Callable

from . import __version__
from .core.events import EventType

log = logging.getLogger("ultron.console")
EXIT_WORDS = {"sair", "exit", "quit", "encerrar o console", "fechar o console"}
LINE = "=" * 44


class Console:
    def __init__(self, core, *, read: Callable[[str], str] | None = None, out: Callable[[str], None] | None = None,
                 voice_wait: float = 20.0):
        self.core = core
        self.read = read or (lambda prompt: input(prompt))
        self._out = out
        self.voice_wait = voice_wait
        self._lock = threading.Lock()
        self._answered = threading.Event()
        self._at_prompt = False
        self._subs: list = []
        self.name = "VOCÊ"
        self.exit_code = 0

    # ------------------------------------------------------------ saída
    def say(self, text: str = "") -> None:
        with self._lock:
            if self._at_prompt:                       # aviso que chegou sozinho: não escreve em cima do prompt
                self._write("")
            self._write(text)
            if self._at_prompt:
                self._write(f"{self.name} > ", end=False)

    def _write(self, text: str, end: bool = True) -> None:
        if self._out is not None:
            self._out(text)
            return
        try:
            sys.stdout.write(text + ("\n" if end else ""))
            sys.stdout.flush()
        except (AttributeError, ValueError, OSError):
            pass

    # ------------------------------------------------------------ eventos do núcleo
    def _on_response(self, event) -> None:
        payload = event.payload
        text = str(payload.get("text", "")).strip()
        if not text:
            return
        if payload.get("partial"):
            self.say(f"JARVIS … {text}")
            return
        self.say(f"JARVIS > {text}")
        self.say()
        if payload.get("source") in ("text", "console"):
            self._answered.set()

    def _on_authorization(self, event) -> None:
        req = event.payload
        scope = f" [{req['category_label']}]" if req.get("category_label") else ""
        options = '"sim", "não" ou "sim, sempre" (24 h)' if req.get("standing_allowed") else '"sim" ou "não"'
        seconds = int(req.get("seconds_left") or 30)
        self.say(f"[CONFIRMAÇÃO]{scope} {req.get('description', '')}")
        self.say(f"              Responda {options}. Sem resposta em {seconds} s = não.")
        self._answered.set()

    def _on_input(self, event) -> None:
        payload = event.payload
        if payload.get("source") == "voice":           # o que a voz entendeu aparece como pedido
            self.say(f"{self.name} (voz) > {payload.get('text', '')}")

    def _on_shutdown(self, _event) -> None:           # "encerre o JARVIS" (o executor já confirmou)
        def finish() -> None:
            time.sleep(1.0)                           # "Encerrando, senhor." chega antes
            self._close("encerramento pedido ao JARVIS")
            os._exit(0)

        threading.Thread(target=finish, name="ultron-console-exit", daemon=True).start()

    # ------------------------------------------------------------ estado real para o cabeçalho
    def banner(self) -> list[str]:
        from .config import paths
        core = self.core
        statuses = core.lifecycle.statuses()
        failed = [n for n, s in statuses.items() if s == "FAILED"]
        system = "ONLINE" if core.booted else "INICIANDO"
        if failed:
            system += f" — com falha: {', '.join(failed)}"
        try:
            models = core.router.status().to_dict()
        except Exception as exc:
            models = {"ollama_alive": False, "error": str(exc), "selections": {}}
        if models.get("ollama_alive"):
            chosen = (models["selections"].get("text") or {}).get("model") or "nenhum modelo de texto instalado"
            model = f"{chosen} (Ollama local{' ' + models['version'] if models.get('version') else ''})"
        else:
            model = ("Ollama indisponível — conversa livre e TARDIS com modelo ficam fora; comandos diretos, "
                     "lembretes e memória funcionam")
        memory = core.lifecycle.health_of("memory")
        memory_text = (f"CONECTADA — {paths.database_path()}" if memory.status != "FAIL"
                       else f"COM FALHA — {memory.detail}")
        tardis = core.lifecycle.health_of("tardis")
        tardis_text = "DISPONÍVEL" if tardis.status in ("OK", "UNKNOWN") else f"{tardis.status} — {tardis.detail}"
        return [LINE, f"       J.A.R.V.I.S. {'.'.join(__version__.split('.')[:2])}", "       CONSOLE INTERFACE", LINE,
                "", f"Sistema: {system}", f"Modelo: {model}", f"Memória: {memory_text}", f"TARDIS: {tardis_text}",
                f"Voz: {self.voice_text()}", ""]

    def voice_text(self) -> str:
        core = self.core
        if not core.enable_voice:
            return "DESATIVADA nesta execução (--no-voice)"
        voice = core.voice
        if core.privacy_shield:
            return "MICROFONE FECHADO (modo privacidade)"
        if voice.stt is not None and voice.capturing:
            return 'DISPONÍVEL — diga "Jarvis" e o pedido'
        reason = voice.stt_reason or voice.reason or "ainda carregando"
        speaker = "a fala do JARVIS continua" if getattr(core, "voice_output_ready", False) else "respostas só em texto"
        return f"INDISPONÍVEL para ouvir ({reason}); {speaker}; digite os pedidos"

    def _wait_voice(self) -> None:
        if not self.core.enable_voice:
            return
        voice = self.core.voice
        deadline = time.monotonic() + self.voice_wait
        noted = False
        while time.monotonic() < deadline:
            stt_done = voice.stt is not None or bool(voice.stt_reason)
            mic_done = voice.capturing or bool(voice.reason) or not voice.mic_enabled
            if stt_done and mic_done:
                return
            if not noted:
                self.say("Carregando o reconhecimento de fala…")
                noted = True
            time.sleep(0.2)

    # ------------------------------------------------------------ laço
    def run(self, *, boot: bool = True) -> int:
        core = self.core
        bus = core.bus
        self._subs = [bus.subscribe(EventType.RESPONSE_READY, self._on_response, name="console"),
                      bus.subscribe(EventType.AUTHORIZATION_REQUIRED, self._on_authorization, name="console.auth"),
                      bus.subscribe(EventType.USER_INPUT, self._on_input, name="console.input"),
                      bus.subscribe(EventType.SHUTDOWN_REQUESTED, self._on_shutdown, name="console.shutdown")]
        if boot and not core.booted:
            self.say("Iniciando o JARVIS…")
            core.boot(on_progress=lambda name, status: self.say(f"  componente {name}: FALHOU (detalhes no log)")
                      if status == "FAILED" else None)
        self._wait_voice()
        try:
            name = core.memory.preferences.get("profile_name")
        except Exception:
            name = None
        self.name = " ".join(str(name).split()).upper() if name else "VOCÊ"
        for row in self.banner():
            self.say(row)
        self.say('JARVIS aguardando instruções. ("sair" encerra · "cancelar" ou Ctrl+C interrompe · '
                 '"sim"/"não" respondem às confirmações)')
        self.say()
        self._watch_stop()
        try:
            self._loop()
        finally:
            self._close("sair")
        return self.exit_code

    def _loop(self) -> None:
        timeout = float(getattr(self.core.settings(), "llm_timeout", 120.0)) + 30.0
        while True:
            with self._lock:
                self._at_prompt = True
            try:
                line = self.read(f"{self.name} > ")
            except EOFError:                            # entrada fechada: encerra como "sair"
                self._at_prompt = False
                log.info("console: fim da entrada (EOF) — encerrando")
                self._write("")
                self._write("(fim da entrada)")
                return
            except KeyboardInterrupt:
                self._at_prompt = False
                log.info("console: Ctrl+C no prompt — encerrando")
                self.say()
                return
            with self._lock:
                self._at_prompt = False
            text = " ".join(str(line).split())
            if not text:
                continue
            if text.casefold() in EXIT_WORDS:
                return
            self._answered.clear()
            if not self.core.submit(text, source="text"):
                continue
            self._wait_answer(timeout)

    def _wait_answer(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self._answered.wait(0.2):
                    return
            except KeyboardInterrupt:                   # Ctrl+C durante a espera: cancela o pedido, não sai
                self.say("[cancelando o pedido em andamento…]")
                self.core.cancel("cancelado pelo usuário (Ctrl+C)")
                deadline = min(deadline, time.monotonic() + 10.0)
        self.say(f"[sem resposta em {timeout:.0f} s — o pedido segue em segundo plano; \"cancelar\" o interrompe]")

    def _watch_stop(self) -> None:
        from .platform import control

        def watch() -> None:                            # START_JARVIS.bat --stop: encerra normalmente
            while self.core.booted:
                if control.stop_requested():
                    control.clear_stop_request()
                    with self._lock:
                        self._at_prompt = False
                    self._write("")
                    self._write("Encerrando a pedido (--stop)…")
                    self._close("--stop")
                    os._exit(0)
                time.sleep(1.0)

        threading.Thread(target=watch, name="ultron-stop-watch", daemon=True).start()

    def _close(self, reason: str) -> None:
        with self._lock:
            self._at_prompt = False
        if not self.core.booted:
            return
        self._write("Encerrando o JARVIS (memória, lembretes e voz fechados em ordem)…")
        log.info("console: encerrando (%s)", reason)
        for sub in self._subs:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        self.core.shutdown()
        from .platform import control
        control.unregister()
        self._write("Até logo.")


def run_console(core, **kwargs) -> int:
    return Console(core, **kwargs).run()
