"""Unit tests for the CLI sync entrypoint."""

from pathlib import Path
from typing import Any

import pytest

from ufs_chem_pr_review_mcp.cli.sync import main


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "ufs-chem-pr-review-sync" in captured.out or "usage:" in captured.out.lower()


def test_cli_missing_config(tmp_path: Path) -> None:
    nonexistent = tmp_path / "nope.yaml"
    with pytest.raises(SystemExit) as exc_info:
        main(["--config", str(nonexistent)])
    assert exc_info.value.code != 0


def test_cli_invalid_yaml_config(tmp_path: Path) -> None:
    bad_cfg = tmp_path / "bad.yaml"
    bad_cfg.write_text("invalid_yaml: [", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(["--config", str(bad_cfg)])
    assert exc_info.value.code != 0


def test_cli_full_run_with_pruning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "cli_test.sqlite3"
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(
        """
repositories:
  - name: test/repoA
    url: https://github.com/test/repoA
    default_branch: main
    enabled: true
  - name: test/repoB
    url: https://github.com/test/repoB
    default_branch: develop
    enabled: false
""",
        encoding="utf-8",
    )

    # Mock sync_repository to avoid network
    def mock_sync(*args: Any, **kwargs: Any) -> int:
        return 5

    monkeypatch.setattr("ufs_chem_pr_review_mcp.cli.sync.sync_repository", mock_sync)

    ret = main(
        [
            "--config",
            str(cfg_file),
            "--db",
            str(db_file),
            "--token",
            "mock_token",
            "--repo",
            "test/repoA",
            "--retention-days",
            "30",
            "--max-records",
            "10",
        ]
    )
    assert ret == 0


def test_cli_no_matching_repos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "cli_test.sqlite3"
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(
        """
repositories:
  - name: test/repoA
    url: https://github.com/test/repoA
    default_branch: main
    enabled: false
""",
        encoding="utf-8",
    )
    ret = main(
        [
            "--config",
            str(cfg_file),
            "--db",
            str(db_file),
            "--token",
            "mock_token",
        ]
    )
    assert ret == 0


def test_cli_sync_error_handling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "cli_test.sqlite3"
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(
        """
repositories:
  - name: test/repoFail
    url: https://github.com/test/repoFail
    default_branch: main
    enabled: true
""",
        encoding="utf-8",
    )

    def mock_fail(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("Network boom")

    monkeypatch.setattr("ufs_chem_pr_review_mcp.cli.sync.sync_repository", mock_fail)
    ret = main(
        [
            "--config",
            str(cfg_file),
            "--db",
            str(db_file),
            "--token",
            "mock_token",
        ]
    )
    assert ret == 0


def test_cli_blocked_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "cli_test.sqlite3"
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(
        """
repositories:
  - name: test/repoA
    url: https://github.com/test/repoA
    default_branch: main
    enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ufs_chem_pr_review_mcp.cli.sync.resolve_github_token",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--config",
                str(cfg_file),
                "--db",
                str(db_file),
            ]
        )
    assert exc_info.value.code == 1


def test_cli_token_via_gh_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "cli_test.sqlite3"
    cfg_file = tmp_path / "repos.yaml"
    cfg_file.write_text(
        """
repositories:
  - name: test/repoA
    url: https://github.com/test/repoA
    default_branch: main
    enabled: true
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "ufs_chem_pr_review_mcp.cli.sync.resolve_github_token",
        lambda *args, **kwargs: "token_from_gh",
    )
    monkeypatch.setattr(
        "ufs_chem_pr_review_mcp.cli.sync.sync_repository", lambda *args, **kwargs: 1
    )

    ret = main(
        [
            "--config",
            str(cfg_file),
            "--db",
            str(db_file),
        ]
    )
    assert ret == 0
