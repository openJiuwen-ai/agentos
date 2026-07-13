"""Logging configuration — file handler with rotation."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings


def setup_file_logging(
    logger_name: str = "app",
) -> logging.Logger:
    """Add a RotatingFileHandler to the specified logger."""
    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger
