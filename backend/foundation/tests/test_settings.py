from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from safra_foundation.errors import ConfigError
from safra_foundation.settings import default_data_dir, load_from_env, parse_bool


class Exemplo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    port: int = Field(default=1234, ge=1024)
    debug: bool = False
    name: str = "x"


def test_variables_are_read_with_the_prefix_and_typed():
    s = load_from_env(Exemplo, "APP_", {"APP_PORT": "5000", "APP_DEBUG": "sim", "OUTRA_PORT": "1"})
    assert (s.port, s.debug, s.name) == (5000, True, "x")


def test_overrides_win_and_empty_values_are_ignored():
    assert load_from_env(Exemplo, "APP_", {"APP_PORT": ""}, port=2000).port == 2000


@pytest.mark.parametrize("env", [{"APP_PORT": "80"}, {"APP_PORT": "abc"}, {"APP_DEBUG": "talvez"}])
def test_invalid_values_raise_config_error(env):
    with pytest.raises(ConfigError):
        load_from_env(Exemplo, "APP_", env)


def test_error_names_the_field_but_never_echoes_the_value():
    with pytest.raises(ConfigError) as info:
        load_from_env(Exemplo, "APP_", {"APP_PORT": "senha-secreta-123"})
    assert "port" in info.value.message and "senha-secreta-123" not in info.value.message
    assert info.value.details["fields"] == ["port"]


def test_unknown_fields_are_rejected():
    with pytest.raises(ConfigError):
        load_from_env(Exemplo, "APP_", {}, inexistente=1)


def test_parse_bool_accepts_portuguese_and_english():
    assert parse_bool("X", "Sim") and parse_bool("X", "true") and not parse_bool("X", "não") and not parse_bool("X", "0")


def test_default_data_dir_per_platform():
    assert default_data_dir("SAFRA", {"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}, platform="win32").name == "SAFRA"
    assert default_data_dir("SAFRA", {"XDG_DATA_HOME": "/home/x/.local/share"}, platform="linux") == Path(
        "/home/x/.local/share/safra")
