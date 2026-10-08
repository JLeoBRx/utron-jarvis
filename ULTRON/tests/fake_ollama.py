"""Servidor HTTP que imita a API do Ollama para testes de integração.

Não é um *mock* de função: o cliente real do ULTRON fala HTTP com este servidor,
exercitando serialização, *streaming*, erros e cancelamento.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class FakeOllama:
    def __init__(self, models: list[str] | None = None, *, vision_models: tuple = ("qwen2.5vl:3b",),
                 responder: Callable[[dict], Any] | None = None, chunk_delay: float = 0.0):
        self.models = list(models if models is not None else ["qwen2.5:3b", "qwen2.5vl:3b"])
        self.vision_models = set(vision_models)
        self.responder = responder or (lambda payload: "Entendido.")
        self.chunk_delay = chunk_delay
        self.requests: list[dict] = []
        self.loaded: list[str] = []               # modelos "carregados" (para /api/ps)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> "FakeOllama":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silencioso
                pass

            def _send_json(self, obj: Any, status: int = 200) -> None:
                body = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                owner.requests.append({"method": "GET", "path": self.path})
                if self.path == "/api/tags":
                    self._send_json({"models": [
                        {"name": m, "model": m, "size": 1000,
                         "details": {"family": m.split(":")[0], "families": [m.split(":")[0]],
                                     "parameter_size": "3B", "quantization_level": "Q4_K_M"}}
                        for m in owner.models]})
                elif self.path == "/api/version":
                    self._send_json({"version": "0.0-fake"})
                elif self.path == "/api/ps":
                    self._send_json({"models": [{"name": m, "model": m, "size": 2000, "size_vram": 2000}
                                                for m in owner.loaded]})
                else:
                    self._send_json({"error": "not found"}, 404)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append({"method": "POST", "path": self.path, "payload": payload})
                if self.path == "/api/show":
                    name = payload.get("model")
                    if name not in owner.models:
                        self._send_json({"error": f"model '{name}' not found"}, 404)
                        return
                    caps = ["completion", "tools"]
                    if name in owner.vision_models:
                        caps.append("vision")
                    self._send_json({"capabilities": caps, "details": {}})
                    return
                if self.path != "/api/chat":
                    self._send_json({"error": "not found"}, 404)
                    return
                model = payload.get("model")
                if model not in owner.models:
                    self._send_json({"error": f"model '{model}' not found, try pulling it first"}, 404)
                    return
                result = owner.responder(payload)
                if isinstance(result, dict):
                    content = result.get("content", "")
                    tool_calls = result.get("tool_calls")
                else:
                    content, tool_calls = str(result), None
                if not payload.get("stream", True):
                    message = {"role": "assistant", "content": content}
                    if tool_calls:
                        message["tool_calls"] = tool_calls
                    self._send_json({"model": model, "message": message, "done": True})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                pieces = [content[i:i + 12] for i in range(0, len(content), 12)] or [""]
                try:
                    for piece in pieces:
                        self._chunk({"model": model, "message": {"role": "assistant", "content": piece},
                                     "done": False})
                        if owner.chunk_delay:
                            time.sleep(owner.chunk_delay)
                    final = {"model": model, "message": {"role": "assistant", "content": ""},
                             "done": True, "eval_count": len(pieces)}
                    if tool_calls:
                        final["message"]["tool_calls"] = tool_calls
                    self._chunk(final)
                    self.wfile.write(b"0\r\n\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _chunk(self, obj: dict) -> None:
                data = (json.dumps(obj) + "\n").encode("utf-8")
                self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "FakeOllama":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def chat_requests(self) -> list[dict]:
        return [r["payload"] for r in self.requests if r.get("path") == "/api/chat"]
