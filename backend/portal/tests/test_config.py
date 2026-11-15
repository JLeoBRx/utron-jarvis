import pytest

from safra_foundation.errors import ConfigError
from safra_portal.config import load_settings


def test_defaults_for_development(tmp_path):
    s = load_settings(env={}, data_dir=tmp_path)
    assert s.database_url == "sqlite:///" + (tmp_path / "portal.sqlite3").as_posix()
    assert s.media_dir == tmp_path / "media" and s.port == 47900
    assert s.public_base_url == "http://127.0.0.1:47900" and not s.secure_cookies


def test_production_requires_postgresql_and_https(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_PORTAL_ENVIRONMENT": "production", "SAFRA_PORTAL_PUBLIC_BASE_URL": "https://safra.example"},
                      data_dir=tmp_path)
    assert "PostgreSQL" in info.value.message
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_PORTAL_ENVIRONMENT": "production", "SAFRA_PORTAL_PUBLIC_BASE_URL": "http://safra.example",
                           "SAFRA_PORTAL_DATABASE_URL": "postgresql+psycopg://u@db/portal"}, data_dir=tmp_path)
    assert "HTTPS" in info.value.message
    ok = load_settings(env={"SAFRA_PORTAL_ENVIRONMENT": "production", "SAFRA_PORTAL_PUBLIC_BASE_URL": "https://safra.example/",
                            "SAFRA_PORTAL_DATABASE_URL": "postgresql+psycopg://u@db/portal"}, data_dir=tmp_path)
    assert ok.secure_cookies and ok.allowed_hosts == ("safra.example",) and ok.allowed_origins == ("https://safra.example",)


@pytest.mark.parametrize("url", ["ftp://x", "safra.example", "https://safra.example/caminho", "javascript:alert(1)"])
def test_public_base_url_must_be_a_plain_origin(tmp_path, url):
    with pytest.raises(ConfigError):
        load_settings(env={"SAFRA_PORTAL_PUBLIC_BASE_URL": url}, data_dir=tmp_path)


def test_assistant_variables_do_not_configure_the_portal(tmp_path):
    s = load_settings(env={"SAFRA_DATABASE_URL": "sqlite:////tmp/assistente.sqlite3", "SAFRA_DATA_DIR": "/tmp/assistente",
                           "SAFRA_API_PORT": "50000"}, data_dir=tmp_path)
    assert "assistente" not in s.database_url and s.port == 47900


def test_error_message_never_echoes_the_database_url(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_PORTAL_PORT": "postgresql://usuario:senha-secreta@db/x"}, data_dir=tmp_path)
    assert "senha-secreta" not in info.value.message
