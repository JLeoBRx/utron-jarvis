"""Logs estruturados: uma linha JSON por evento, com identificador de correlação e segredos mascarados."""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
import secrets
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

LOGGER_NAME = "safra"
correlation_id: ContextVar[str] = ContextVar("safra_correlation_id", default="")

_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime", "taskName"}
_SECRET_PATTERNS = (
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{12,}"), "[segredo]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/\-]{12,}=*"), r"\1 [segredo]"),
    (re.compile(r"(?i)\b(password|passwd|senha|secret|segredo|token|api[_-]?key|chave)\b(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
     r"\1\2[segredo]"),
)


def new_correlation_id() -> str:
    return "c-" + secrets.token_hex(8)


def mask_secrets(text: str) -> str:
    """Remove do texto o que parece credencial. É uma rede de segurança: segredo não deveria chegar ao log."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": mask_secrets(record.getMessage()),
        }
        cid = correlation_id.get()
        if cid:
            entry["correlation_id"] = cid
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = mask_secrets(value) if isinstance(value, str) else value
        if record.exc_info:
            entry["exception"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(*, level: str = "INFO", logs_dir: Path | None = None, console: bool = True) -> logging.Logger:
    """Configura o registrador ``safra``. Pode ser chamada de novo: substitui os destinos anteriores."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)
    logger.propagate = False
    if logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(logs_dir / "safra.jsonl", maxBytes=5_000_000, backupCount=5,
                                                            encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(JsonFormatter())
        logger.addHandler(stream)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)
