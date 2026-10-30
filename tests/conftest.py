"""Shared pytest fixtures for ufs-chem-pr-review-mcp tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a path to a temporary SQLite database file."""
    return tmp_path / "test_reviews.sqlite3"
