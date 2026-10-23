"""Tests for standardized logging module."""

import io
import logging
import sys

from ufs_chem_pr_review_mcp.logs import (
    LOGGER_NAME,
    configure_logging,
    get_logger,
)


def test_get_logger_namespacing() -> None:
    logger = get_logger("test_module")
    assert logger.name == f"{LOGGER_NAME}.test_module"
    assert isinstance(logger, logging.Logger)


def test_configure_logging_stderr_routing() -> None:
    stream = io.StringIO()
    # Reset root logger handlers for testing
    root = logging.getLogger(LOGGER_NAME)
    root.handlers.clear()

    configure_logging(level="DEBUG", stream=stream)
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1

    logger = get_logger("emitter")
    logger.debug("debug message 123")
    output = stream.getvalue()
    assert "debug message 123" in output
    assert "DEBUG" in output
    assert f"{LOGGER_NAME}.emitter" in output


def test_configure_logging_idempotent() -> None:
    stream = io.StringIO()
    root = logging.getLogger(LOGGER_NAME)
    root.handlers.clear()

    configure_logging(level="INFO", stream=stream)
    configure_logging(level="INFO", stream=stream)
    assert len(root.handlers) == 1


def test_configure_logging_default_stream() -> None:
    root = logging.getLogger(LOGGER_NAME)
    root.handlers.clear()
    configure_logging(level="WARNING")
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
