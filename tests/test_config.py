"""Tests for configuration settings and repositories loader."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ufs_chem_pr_review_mcp.config import (
    RepoConfig,
    Settings,
    load_repositories_config,
)


def test_repo_config_valid() -> None:
    repo = RepoConfig(
        name="ufs-community/CATChem",
        url="https://github.com/ufs-community/CATChem",
        default_branch="develop",
        enabled=True,
    )
    assert repo.name == "ufs-community/CATChem"
    assert repo.default_branch == "develop"
    assert repo.enabled is True


def test_repo_config_frozen_and_forbid_extra() -> None:
    repo = RepoConfig(
        name="test/repo",
        url="https://github.com/test/repo",
    )
    with pytest.raises(ValidationError):
        repo.name = "new/name"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        RepoConfig(
            name="test/repo",
            url="https://github.com/test/repo",
            extra_field="disallowed",  # type: ignore[call-arg]
        )


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("UFS_CHEM_LOG_LEVEL", raising=False)
    settings = Settings()
    assert settings.log_level == "INFO"
    assert settings.github_token is None
    assert settings.db_path == Path("data/ufs_chem_reviews.sqlite3")


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UFS_CHEM_GITHUB_TOKEN", "ghp_mock123")
    monkeypatch.setenv("UFS_CHEM_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("UFS_CHEM_RETENTION_DAYS", "90")
    settings = Settings()
    assert settings.github_token == "ghp_mock123"
    assert settings.log_level == "DEBUG"
    assert settings.retention_days == 90


def test_load_repositories_config_existing(tmp_path: Path) -> None:
    yaml_content = """
repositories:
  - name: test/repo1
    url: https://github.com/test/repo1
    default_branch: main
    enabled: true
"""
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")
    loaded = load_repositories_config(cfg_file)
    assert len(loaded.repositories) == 1
    assert loaded.repositories[0].name == "test/repo1"


def test_load_repositories_config_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError):
        load_repositories_config(missing)


def test_load_repositories_config_invalid_yaml(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("repositories: not_a_list", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_repositories_config(bad_file)
