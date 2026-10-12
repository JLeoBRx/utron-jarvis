"""Cliente do Ollama — o único caminho de chamada ao modelo local.

* Somente biblioteca padrão (``urllib``).
* ``chat`` usa *streaming* para permitir cancelamento real no meio da geração.
* Erros são classificados (``OllamaError.kind``) para o Recovery Engine.
* No modo de privacidade local, endereços que não sejam da própria máquina são recusados.
* Nunca devolve resposta inventada: falha é sempre exceção.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

log = logging.getLogger("ultron.ollama")

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class OllamaError(RuntimeError):
    """Falha do Ollama com tipo classificado.

    kind: UNAVAILABLE | MODEL_MISSING | TIMEOUT | BAD_RESPONSE | CANCELLED | BLOCKED | HTTP
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class ModelInfo:
    name: str
    family: str = ""
    families: tuple = ()
    parameter_size: str = ""
    quantization: str = ""
    size_bytes: int = 0
    capabilities: tuple = ()

    def to_dict(self) -> dict:
        return {"name": self.name, "family": self.family, "families": list(self.families),
                "parameter_size": self.parameter_size, "quantization": self.quantization,
                "size_bytes": self.size_bytes, "capabilities": list(self.capabilities)}


@dataclass
class ChatResult:
    content: str
    tool_calls: list = field(default_factory=list)
    model: str = ""
    seconds: float = 0.0
    eval_count: int = 0

    def message(self) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


def is_local_url(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host in LOCAL_HOSTS


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", *, timeout: float = 120.0,
                 local_only: Callable[[], bool] | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self._local_only = local_only or (lambda: True)
        self.last_latency_ms: float | None = None
        self.last_error: str = ""
        self.metrics = None                   # PerformanceMonitor (opcional): latência e inferência reais

    # ------------------------------------------------------------ transporte
    def _guard(self) -> None:
        if self._local_only() and not is_local_url(self.base_url):
            raise OllamaError("BLOCKED", "Modo local ativo: o ULTRON só aceita Ollama nesta máquina "
                                         f"(endereço configurado: {self.base_url}).")

    def _request(self, path: str, payload: dict | None = None, *, timeout: float | None = None,
                 method: str | None = None):
        self._guard()
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method=method or ("POST" if data is not None else "GET"))
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if exc.code == 404 and "not found" in body.lower():
                raise OllamaError("MODEL_MISSING", body or "modelo não encontrado") from exc
            raise OllamaError("HTTP", f"HTTP {exc.code}: {body}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaError("TIMEOUT", f"Ollama não respondeu em {timeout or self.timeout:.0f}s") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise OllamaError("TIMEOUT", "tempo esgotado ao contatar o Ollama") from exc
            raise OllamaError("UNAVAILABLE", f"Ollama inacessível em {self.base_url}: {reason}") from exc
        except OSError as exc:
            raise OllamaError("UNAVAILABLE", f"Ollama inacessível: {exc}") from exc

    def _json(self, path: str, payload: dict | None = None, *, timeout: float | None = None) -> dict:
        started = time.perf_counter()
        with self._request(path, payload, timeout=timeout) as response:
            raw = response.read()
        self.last_latency_ms = (time.perf_counter() - started) * 1000.0
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise OllamaError("BAD_RESPONSE", "resposta do Ollama não é JSON") from exc

    # ------------------------------------------------------------ consultas
    def version(self, timeout: float = 2.0) -> str:
        return str(self._json("/api/version", timeout=timeout).get("version", ""))

    def is_alive(self, timeout: float = 1.5) -> bool:
        try:
            self._json("/api/tags", timeout=timeout)
            self.last_error = ""
            return True
        except OllamaError as exc:
            self.last_error = str(exc)
            return False

    def list_models(self, timeout: float = 3.0) -> list[ModelInfo]:
        body = self._json("/api/tags", timeout=timeout)
        models = []
        for item in body.get("models") or []:
            details = item.get("details") or {}
            models.append(ModelInfo(
                name=str(item.get("name") or item.get("model") or ""),
                family=str(details.get("family") or ""),
                families=tuple(details.get("families") or ()),
                parameter_size=str(details.get("parameter_size") or ""),
                quantization=str(details.get("quantization_level") or ""),
                size_bytes=int(item.get("size") or 0),
            ))
        return [m for m in models if m.name]

    def running_models(self, timeout: float = 2.0) -> list[dict]:
        """Modelos carregados agora (``/api/ps``): tamanho e quanto está na GPU (VRAM)."""
        body = self._json("/api/ps", timeout=timeout)
        out = []
        for item in body.get("models") or []:
            size, vram = int(item.get("size") or 0), int(item.get("size_vram") or 0)
            out.append({"name": str(item.get("name") or item.get("model") or ""), "size": size, "size_vram": vram,
                        "gpu_fraction": round(vram / size, 2) if size else 0.0,
                        "expires_at": item.get("expires_at", "")})
        return out

    def show(self, model: str, timeout: float = 5.0) -> dict:
        return self._json("/api/show", {"model": model}, timeout=timeout)

    def capabilities(self, model: str) -> tuple:
        """Capacidades declaradas pelo Ollama (versões recentes): completion, vision, tools..."""
        try:
            info = self.show(model)
        except OllamaError:
            return ()
        caps = info.get("capabilities")
        if isinstance(caps, list):
            return tuple(str(c) for c in caps)
        return ()

    # ------------------------------------------------------------ geração
    def chat_stream(self, model: str, messages: list[dict], *, tools: list | None = None,
                    fmt: str | dict | None = None, options: dict | None = None,
                    timeout: float | None = None, cancel=None, keep_alive: str | None = None) -> Iterator[dict]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        if fmt:
            payload["format"] = fmt
        if options:
            payload["options"] = options
        if keep_alive:
            payload["keep_alive"] = keep_alive
        response = self._request("/api/chat", payload, timeout=timeout)
        try:
            for raw in response:
                if cancel is not None and getattr(cancel, "cancelled", False):
                    raise OllamaError("CANCELLED", "geração cancelada")
                line = raw.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except ValueError as exc:
                    raise OllamaError("BAD_RESPONSE", "fragmento inválido do Ollama") from exc
                if chunk.get("error"):
                    message = str(chunk["error"])
                    kind = "MODEL_MISSING" if "not found" in message.lower() else "BAD_RESPONSE"
                    raise OllamaError(kind, message)
                yield chunk
                if chunk.get("done"):
                    break
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaError("TIMEOUT", "o modelo parou de responder") from exc
        finally:
            response.close()

    def chat(self, model: str, messages: list[dict], *, tools: list | None = None,
             fmt: str | dict | None = None, options: dict | None = None, timeout: float | None = None,
             cancel=None, on_token: Callable[[str], None] | None = None) -> ChatResult:
        started = time.perf_counter()
        parts: list[str] = []
        tool_calls: list = []
        eval_count = 0
        timings: dict = {}
        for chunk in self.chat_stream(model, messages, tools=tools, fmt=fmt, options=options,
                                      timeout=timeout, cancel=cancel):
            message = chunk.get("message") or {}
            piece = message.get("content") or ""
            if piece:
                parts.append(piece)
                if on_token:
                    on_token(piece)
            if message.get("tool_calls"):
                tool_calls.extend(message["tool_calls"])
            if chunk.get("done"):
                eval_count = int(chunk.get("eval_count") or 0)
                timings = {k: chunk.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration",
                                                     "eval_duration") if isinstance(chunk.get(k), (int, float))}
        seconds = time.perf_counter() - started
        self.last_latency_ms = seconds * 1000.0
        self._record(seconds, timings)
        return ChatResult("".join(parts).strip(), tool_calls, model, seconds, eval_count)

    def _record(self, seconds: float, timings: dict) -> None:
        """Latência total da chamada e, quando o Ollama informa, o tempo de inferência separado
        (avaliação do prompt + geração), a carga do modelo e o restante (rede, fila, serialização)."""
        if self.metrics is None:
            return
        self.metrics.record("model.request", seconds)
        if "eval_duration" in timings or "prompt_eval_duration" in timings:
            inference = (timings.get("prompt_eval_duration", 0) + timings.get("eval_duration", 0)) / 1e9
            self.metrics.record("model.inference", inference)
        if timings.get("load_duration"):
            self.metrics.record("model.load", timings["load_duration"] / 1e9)
        if timings.get("total_duration"):
            self.metrics.record("model.overhead", max(0.0, seconds - timings["total_duration"] / 1e9))

    # ------------------------------------------------------------ servidor
    @staticmethod
    def find_executable() -> str | None:
        exe = shutil.which("ollama")
        if exe:
            return exe
        if sys.platform == "win32":
            candidate = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
            if os.path.isfile(candidate):
                return candidate
        return None

    def ensure_server(self, *, autostart: bool = True, wait_seconds: float = 20.0, cancel=None) -> bool:
        """Garante o servidor local. Se ausente e permitido, executa ``ollama serve``."""
        if self.is_alive():
            return True
        if not autostart or not is_local_url(self.base_url):
            return False
        exe = self.find_executable()
        if not exe:
            self.last_error = "executável do Ollama não encontrado"
            return False
        flags = 0
        if sys.platform == "win32":
            flags = 0x08000000 | 0x00000008          # CREATE_NO_WINDOW | DETACHED_PROCESS
        try:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
            log.info("ollama serve iniciado automaticamente")
        except OSError as exc:
            self.last_error = f"falha ao iniciar o Ollama: {exc}"
            return False
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if cancel is not None and getattr(cancel, "cancelled", False):
                return False
            if self.is_alive():
                return True
            time.sleep(0.5)
        return False
