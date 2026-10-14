"""Logging: console (INFO) + rotating file logs/cineverse.log (DEBUG, 1 MB × 3), request ids,
and masking of secret values.

Spec: CineVerse_Logging_Tracing_and_Observability §2; Configuration §6.
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
SECRET_RE = re.compile(r"(\b\w*_KEY\s*[=:]\s*)\S+")
_configured = False


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class _MaskSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = SECRET_RE.sub(r"\1***", message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


def configure(log_dir: Path = Path("logs")) -> None:
    """Configure the 'cineverse' logger once; level from CINEVERSE_LOG_LEVEL (default INFO)."""
    global _configured
    if _configured:
        return
    logger = logging.getLogger("cineverse")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(FORMAT)
    console = logging.StreamHandler()
    console.setLevel(os.environ.get("CINEVERSE_LOG_LEVEL", "INFO").upper())
    handlers: list[logging.Handler] = [console]
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_dir / "cineverse.log", maxBytes=1_000_000,
                                           backupCount=3, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)
    except OSError:
        pass
    for h in handlers:
        h.setFormatter(formatter)
        h.addFilter(_RequestIdFilter())
        h.addFilter(_MaskSecrets())
        logger.addHandler(h)
    _configured = True


def request_logger(name: str, request_id: str) -> logging.LoggerAdapter[Any]:
    return logging.LoggerAdapter(logging.getLogger(name), {"request_id": request_id})
