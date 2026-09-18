from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_CAMPOS_RESERVADOS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "logger": record.name,
            "nivel": record.levelname,
            "mensagem": record.getMessage(),
        }

        extras = {
            chave: valor
            for chave, valor in record.__dict__.items()
            if chave not in _CAMPOS_RESERVADOS and not chave.startswith("_")
        }
        if extras:
            payload["contexto"] = extras
        if record.exc_info:
            payload["erro"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(nome: str = "oraculo") -> logging.Logger:
    logger = logging.getLogger(nome)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger
