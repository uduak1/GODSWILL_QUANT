"""Structured logging for console + rotating file. UTF-8 safe for Windows."""
from __future__ import annotations
import io
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("godswill")
    logger.setLevel(level.upper())
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — UTF-8
    fh = RotatingFileHandler(
        log_dir / "godswill.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler — force UTF-8 via TextIOWrapper on stdout buffer
    try:
        console_stream = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except (AttributeError, ValueError):
        console_stream = sys.stdout

    ch = logging.StreamHandler(console_stream)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger