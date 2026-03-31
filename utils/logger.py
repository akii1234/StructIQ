"""Logging utilities for the AI Modernization Engine."""

from __future__ import annotations

import json
import logging
import os
from typing import Any


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_file_event(
    logger: logging.Logger,
    file_path: str,
    status: str,
    reason: str = "",
    time_taken: float = 0.0,
    **extra: Any,
) -> None:
    """Write structured per-file processing log."""
    payload: dict[str, Any] = {
        "file": file_path,
        "status": status,
        "reason": reason,
        "time_taken": f"{time_taken:.4f}s",
    }
    payload.update(extra)
    logger.info("%s", json.dumps(payload, ensure_ascii=True))
