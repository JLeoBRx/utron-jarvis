import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from safra_foundation import errors
from safra_foundation.web import CORRELATION_HEADER, create_base_app

HOSTS = ("testserver",)


class Item(BaseModel):
    name: str
    amount: int


def _base(**kwargs):
    app = create_base_app(title="teste", version="0", allowed_hosts=HOSTS, **kwargs)

    @app.post("/echo")
    async def echo(item: Item) -> dict:
        return {"name": item.name}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("detalhe interno: /caminho/secreto senha=abc123456789")

    @app.get("/denied")
    async def denied() -> dict:
        raise errors.Forbidden(details={"permission": "publicar"})

    return app


@pytest.fixture
def base():
    with TestClient(_base(), raise_server_exceptions=False) as client:
        yield client


def _error(response):
    body = response.json()["error"]
    assert body["correlation_id"] == response.headers[CORRELATION_HEADER]
    return body


def test_every_response_carries_correlation_and_security_headers(base):
    response = base.post("/echo", json={"name": "a", "amount": 1})
    assert response.status_code == 200 and response.json() == {"name": "a"}
    assert response.headers[CORRELATION_HEADER].startswith("c-")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    other = base.post("/echo", json={"name": "a", "amount": 1})
    assert other.headers[CORRELATION_HEADER] != response.headers[CORRELATION_HEADER]


def test_security_headers_can_be_set_per_service():
    app = _base(security_headers={"Content-Security-Policy": "default-src 'self'"})
    with TestClient(app) as client:
        response = client.post("/echo", json={"name": "a", "amount": 1})
    assert response.headers["content-security-policy"] == "default-src 'self'"
    assert "x-frame-options" not in response.headers


def test_validation_error_uses_the_single_error_format(base):
    response = base.post("/echo", json={"name": "a", "amount": "muitos"})
    body = _error(response)
    assert response.status_code == 422 and body["code"] == "validacao"
    assert body["details"]["fields"][0]["field"] == "amount"


def test_unknown_route_and_wrong_method(base):
    missing = base.get("/nao-existe")
    assert missing.status_code == 404 and _error(missing)["code"] == "nao_encontrado"
    wrong = base.get("/echo")
    assert wrong.status_code == 405 and _error(wrong)["code"] == "metodo_nao_permitido"


def test_domain_error_keeps_code_status_and_details(base):
    response = base.get("/denied")
    body = _error(response)
    assert response.status_code == 403 and body["code"] == "nao_permitido"
    assert body["details"] == {"permission": "publicar"}


def test_unhandled_exception_becomes_500_without_leaking_anything(base):
    response = base.get("/boom")
    body = _error(response)
    assert response.status_code == 500 and body["code"] == "erro_interno"
    text = json.dumps(response.json())
    assert "caminho" not in text and "abc123456789" not in text and "RuntimeError" not in text
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("host", ["evil.example", "testserver.evil.example", "127.0.0.1:9999", ""])
def test_requests_addressed_to_another_host_are_refused_before_routing(host):
    with TestClient(_base(), raise_server_exceptions=False) as client:
        response = client.post("/echo", json={"name": "a", "amount": 1}, headers={"host": host})
    assert response.status_code == 403 and response.json()["error"]["code"] == "origem_recusada"
    assert CORRELATION_HEADER in response.headers


def test_interactive_docs_are_off_unless_asked():
    with TestClient(_base()) as client:
        assert client.get("/api/docs").status_code == 404 and client.get("/api/openapi.json").status_code == 404
    with TestClient(_base(docs=True)) as client:
        assert client.get("/api/openapi.json").status_code == 200
