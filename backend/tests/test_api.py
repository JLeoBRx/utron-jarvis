import json

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from safra import __version__
from safra.api.app import create_core_app
from safra.api.foundation import CORRELATION_HEADER, create_base_app
from safra.core import errors
from safra.storage import backup

HOSTS = ("testserver",)


class Item(BaseModel):
    name: str
    amount: int


def _base():
    app = create_base_app(title="teste", version="0", allowed_hosts=HOSTS)

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


def _error(response):
    body = response.json()["error"]
    assert body["correlation_id"] == response.headers[CORRELATION_HEADER]
    return body


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
    with TestClient(create_base_app(title="t", version="0", allowed_hosts=HOSTS, docs=True)) as client:
        assert client.get("/api/openapi.json").status_code == 200


# ---------------------------------------------------------------- aplicação do SAFRA Core

def _client(settings):
    return TestClient(create_core_app(settings), base_url=f"http://127.0.0.1:{settings.api_port}")


def test_core_starts_migrates_and_reports_health(settings):
    with _client(settings) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": __version__}       # nada além disso, sem sessão
    assert (settings.data_dir / "safra.sqlite3").is_file()
    assert backup.list_backups(settings.backups_dir) == []                       # banco novo: sem backup


def test_core_restart_keeps_the_database_and_does_not_migrate_again(settings):
    with _client(settings) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
    with _client(settings) as client:
        assert client.get("/api/v1/health").json()["status"] == "ok"
    assert backup.list_backups(settings.backups_dir) == []


def test_core_health_fails_honestly_when_the_schema_is_behind(settings):
    from safra.storage import migrations

    with _client(settings) as client:
        migrations.downgrade(client.app.state.engine, "base", backups_dir=settings.backups_dir)
        assert client.get("/api/v1/health").json()["status"] == "failed"


def test_core_only_answers_to_its_own_address(settings):
    with _client(settings) as client:
        assert client.get("/api/v1/health", headers={"host": "safra.example.com"}).status_code == 403
        assert client.get("/api/v1/health", headers={"host": f"localhost:{settings.api_port}"}).status_code == 200


def test_core_docs_follow_the_environment(settings):
    with _client(settings) as client:                                            # ambiente de teste
        assert client.get("/api/docs").status_code == 404
    development = settings.model_copy(update={"environment": "development"})
    with _client(development) as client:
        assert client.get("/api/openapi.json").status_code == 200


def test_cli_check_and_version(settings, monkeypatch, capsys):
    from safra.api import cli

    monkeypatch.setenv("SAFRA_DATA_DIR", str(settings.data_dir))
    assert cli.main(["--check"]) == 0
    assert "banco na versão 0001" in capsys.readouterr().out
    monkeypatch.setenv("SAFRA_API_HOST", "0.0.0.0")
    assert cli.main(["--check"]) == 2
    assert "SAFRA não iniciou" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"SAFRA {__version__}"
