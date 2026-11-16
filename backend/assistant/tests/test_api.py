import pytest
from fastapi.testclient import TestClient

from safra import __version__
from safra.api.app import create_app
from safra.storage import MIGRATIONS
from safra_foundation import backup, migrations


def _client(settings):
    return TestClient(create_app(settings), base_url=f"http://127.0.0.1:{settings.api_port}")


def test_assistant_starts_migrates_and_reports_health(settings):
    with _client(settings) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "assistant", "version": __version__}
        assert migrations.database_owner(client.app.state.engine) == "assistant"
    assert (settings.data_dir / "safra.sqlite3").is_file()
    assert backup.list_backups(settings.backups_dir, prefix="safra-assistant") == []     # banco novo: sem backup


def test_restart_keeps_the_database_and_does_not_migrate_again(settings):
    for _ in range(2):
        with _client(settings) as client:
            assert client.get("/api/v1/health").json()["status"] == "ok"
    assert backup.list_backups(settings.backups_dir, prefix="safra-assistant") == []


def test_health_fails_honestly_when_the_schema_is_behind(settings):
    with _client(settings) as client:
        migrations.downgrade(client.app.state.engine, MIGRATIONS, "base", backups_dir=settings.backups_dir)
        assert client.get("/api/v1/health").json()["status"] == "failed"


def test_assistant_only_answers_to_its_own_address(settings):
    with _client(settings) as client:
        assert client.get("/api/v1/health", headers={"host": "safra.example.com"}).status_code == 403
        assert client.get("/api/v1/health", headers={"host": f"localhost:{settings.api_port}"}).status_code == 200


def test_docs_follow_the_environment(settings):
    with _client(settings) as client:                                            # ambiente de teste
        assert client.get("/api/docs").status_code == 404
    development = settings.model_copy(update={"environment": "development"})
    with _client(development) as client:
        assert client.get("/api/openapi.json").status_code == 200


def test_cli_check_and_version(settings, monkeypatch, capsys):
    from safra.api import cli

    monkeypatch.setenv("SAFRA_DATA_DIR", str(settings.data_dir))
    assert cli.main(["--check"]) == 0
    assert "ok" in capsys.readouterr().out
    monkeypatch.setenv("SAFRA_API_HOST", "0.0.0.0")
    assert cli.main(["--check"]) == 2
    assert "não iniciou" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"SAFRA Assistant {__version__}"
