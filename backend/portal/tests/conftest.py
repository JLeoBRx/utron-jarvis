"""Apoio aos testes do Portal: banco e mídia em pasta temporária; nenhuma conta existe até o teste criar."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from safra_portal.api.app import create_app
from safra_portal.config import Settings, load_settings
from safra_portal.infrastructure.db import transaction

PASSWORD = "senha de teste bem comprida"


def make_png(width: int = 2, height: int = 2) -> bytes:
    """PNG válido mínimo, gerado aqui (nenhum arquivo binário no repositório)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xe3\x26\x36" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return load_settings(env={}, environment="test", data_dir=tmp_path / "portal", log_to_file=False)


class Portal:
    """Um Portal no ar, com atalhos para criar contas e entrar."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.app = create_app(settings)
        self.origin = settings.public_base_url
        self._context = TestClient(self.app, base_url=self.origin, raise_server_exceptions=False)
        self.public = self._context.__enter__()                 # visitante: sem sessão

    def close(self) -> None:
        self._context.__exit__(None, None, None)

    def client(self) -> TestClient:
        """Outro navegador contra a MESMA aplicação (cookies próprios)."""
        return TestClient(self.app, base_url=self.origin, raise_server_exceptions=False)

    def create_user(self, role: str, email: str | None = None, *, password: str | None = PASSWORD, name: str = "") -> int:
        email = email or f"{role}@exemplo.test"
        with transaction(self.app.state.session_factory) as db:
            user = self.app.state.auth.create_user(db, email=email, name=name or role.capitalize(), role=role,
                                                   password=password)
            return user.id

    def login(self, role: str, email: str | None = None, *, create: bool = True) -> "Admin":
        email = email or f"{role}@exemplo.test"
        if create:
            self.create_user(role, email)
        client = self.client()
        response = client.post("/admin/api/auth/login", json={"email": email, "password": PASSWORD},
                               headers={"Origin": self.origin})
        assert response.status_code == 200, response.text
        return Admin(client, self.origin, response.json()["csrf_token"], response.json())


class Admin:
    """Sessão administrativa: acrescenta Origin e o código anti-CSRF aos pedidos que alteram."""

    def __init__(self, client: TestClient, origin: str, csrf: str, session: dict) -> None:
        self.client, self.origin, self.csrf, self.session = client, origin, csrf, session

    def headers(self) -> dict[str, str]:
        return {"Origin": self.origin, "X-CSRF-Token": self.csrf}

    def get(self, path: str, **kwargs):
        return self.client.get("/admin/api" + path, **kwargs)

    def send(self, method: str, path: str, **kwargs):
        headers = {**self.headers(), **kwargs.pop("headers", {})}
        return self.client.request(method, "/admin/api" + path, headers=headers, **kwargs)

    def post(self, path: str, **kwargs):
        return self.send("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.send("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs):
        return self.send("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.send("DELETE", path, **kwargs)


@pytest.fixture
def portal(settings: Settings):
    instance = Portal(settings)
    yield instance
    instance.close()


def page_data(slug: str = "pagina-de-teste", title: str = "Página de teste", **extra) -> dict:
    return {"slug": slug, "title": title, "summary": "Resumo", "blocks": [{"type": "paragraph", "text": "Texto inicial."}],
            **extra}
