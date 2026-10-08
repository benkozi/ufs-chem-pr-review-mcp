"""Standardized logging for ufs-chem-pr-review-mcp: single namespace, level from settings,
strictly outputting to sys.stderr to guarantee zero stdout pollution for the MCP JSON-RPC transport."""

import logging
import sys
from typing import TextIO

LOGGER_NAME = "ufs_chem_pr_review_mcp"
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the top-level namespace."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure_logging(level: str = "INFO", stream: TextIO = sys.stderr) -> None:
    """Configure the namespace logger once per session (idempotent).
    Guarantees that log messages never touch sys.stdout."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
