"""Servidor HTTP local que imita a Responses API da OpenAI (POST /v1/responses) para testes.

O provedor real do JARVIS fala HTTP com este servidor: serialização, autorização, ferramentas,
erros. Nenhuma chamada sai do computador.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class FakeOpenAI:
    def __init__(self, responder: Callable[[dict], dict] | None = None, *, key: str = "sk-teste-1234567890",
                 status: int = 200):
        self.responder = responder or (lambda payload: {"text": "Resposta da OpenAI."})
        self.key = key
        self.status = status
        self.requests: list[dict] = []
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> "FakeOpenAI":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _send(self, obj: Any, status: int = 200) -> None:
                body = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                owner.requests.append({"path": self.path, "auth": self.headers.get("Authorization", ""),
                                       "payload": payload})
                if self.path != "/v1/responses":
                    return self._send({"error": {"message": "not found"}}, 404)
                if self.headers.get("Authorization") != f"Bearer {owner.key}":
                    return self._send({"error": {"message": "Incorrect API key provided"}}, 401)
                if owner.status != 200:
                    return self._send({"error": {"message": "falha simulada"}}, owner.status)
                answer = owner.responder(payload)
                output = []
                for call in answer.get("calls", []):
                    output.append({"type": "function_call", "id": f"fc_{call['id']}", "call_id": call["id"],
                                   "name": call["name"], "arguments": json.dumps(call.get("arguments", {}))})
                if answer.get("text"):
                    output.append({"type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": answer["text"]}]})
                self._send({"id": "resp_1", "model": payload.get("model"), "output": output,
                            "usage": {"output_tokens": 7}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self) -> "FakeOpenAI":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
