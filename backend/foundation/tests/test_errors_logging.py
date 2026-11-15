import json
import logging

from safra_foundation import errors
from safra_foundation.logging import (JsonFormatter, configure_logging, correlation_id, get_logger, mask_secrets,
                                new_correlation_id)


def test_error_payload_has_the_contract_shape():
    payload = errors.error_payload(errors.NotFound(details={"id": "x"}), "c-1")
    assert payload == {"error": {"code": "nao_encontrado", "message": errors.NotFound.default_message,
                                 "correlation_id": "c-1", "details": {"id": "x"}}}
    assert "details" not in errors.error_payload(errors.Forbidden(), "c-2")["error"]


def test_every_error_has_a_distinct_code_and_a_sane_status():
    kinds = [k for k in vars(errors).values() if isinstance(k, type) and issubclass(k, errors.SafraError)]
    codes = [k.code for k in kinds]
    assert len(codes) == len(set(codes)) and len(kinds) >= 12
    assert all(400 <= k.status <= 599 for k in kinds)


def _line(record_kwargs=None, **extra):
    record = logging.LogRecord("safra.teste", logging.INFO, __file__, 1, "evento %s", ("x",), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_log_line_is_json_with_the_expected_fields():
    token = correlation_id.set("c-abc")
    try:
        entry = _line(user="ana", count=3)
    finally:
        correlation_id.reset(token)
    assert entry["level"] == "INFO" and entry["logger"] == "safra.teste" and entry["message"] == "evento x"
    assert entry["correlation_id"] == "c-abc" and entry["user"] == "ana" and entry["count"] == 3
    assert entry["ts"].endswith("Z")


def test_secrets_are_masked_in_messages_and_fields():
    assert "sk-abcdefghijklmnop" not in mask_secrets("chave sk-abcdefghijklmnop usada")
    assert "hunter2hunter2" not in mask_secrets("password=hunter2hunter2")
    assert "abc.def.ghi-jkl_mno" not in mask_secrets("Authorization: Bearer abc.def.ghi-jkl_mno")
    assert mask_secrets("nada sensível aqui") == "nada sensível aqui"
    entry = _line(detail="token: zzzzzzzzzzzzzzzz")
    assert "zzzzzzzzzzzzzzzz" not in json.dumps(entry)


def test_file_logging_writes_json_lines_and_can_be_reconfigured(tmp_path):
    configure_logging(level="INFO", logs_dir=tmp_path, console=False)
    get_logger("teste").info("primeira", extra={"n": 1})
    configure_logging(level="INFO", logs_dir=tmp_path, console=False)      # reconfigurar não duplica destinos
    get_logger("teste").info("segunda")
    logging.getLogger("safra").handlers[0].flush()
    lines = (tmp_path / "safra.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["message"] for line in lines] == ["primeira", "segunda"]
    configure_logging(level="INFO", logs_dir=None, console=False)


def test_correlation_ids_are_unique():
    assert len({new_correlation_id() for _ in range(200)}) == 200
