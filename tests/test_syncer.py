import subprocess
from pathlib import Path
from typing import Any

import pytest
import respx

from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.ingest.client import (
    GitHubApiError,
    GitHubClient,
    resolve_github_token,
)
from ufs_chem_pr_review_mcp.ingest.syncer import sync_repository


@respx.mock
def test_github_client_get_pull_requests() -> None:
    client = GitHubClient(token="mock_token")
    respx.get("https://api.github.com/repos/ufs-community/CATChem/pulls").respond(
        json=[
            {
                "number": 42,
                "title": "Fix SOA reaction rate",
                "user": {"login": "dev1"},
                "state": "open",
                "base": {"sha": "base123"},
                "head": {"sha": "head456"},
                "created_at": "2026-10-01T00:00:00Z",
                "updated_at": "2026-10-02T00:00:00Z",
                "merged_at": None,
            }
        ]
    )
    prs = client.get_pull_requests("ufs-community/CATChem")
    assert len(prs) == 1
    assert prs[0]["number"] == 42
    assert prs[0]["title"] == "Fix SOA reaction rate"


@respx.mock
def test_github_client_get_pr_diff_standard() -> None:
    client = GitHubClient(token=None)
    mock_diff = "diff --git a/test.py b/test.py\n+x = 1"
    respx.get("https://api.github.com/repos/test/repo/pulls/1").respond(
        text=mock_diff,
        headers={"content-type": "application/vnd.github.v3.diff"},
    )
    diff = client.get_pr_diff("test/repo", 1)
    assert diff == mock_diff


@respx.mock
def test_github_client_get_pr_diff_fallback_large() -> None:
    client = GitHubClient(token=None)
    # Return 406 or too large on standard diff endpoint
    respx.get("https://api.github.com/repos/test/repo/pulls/1").respond(
        status_code=406,
        text="diff is too large",
    )
    # Fallback endpoint /pulls/1/files
    respx.get("https://api.github.com/repos/test/repo/pulls/1/files").respond(
        json=[
            {
                "filename": "src/module.F90",
                "patch": "@@ -1,1 +1,2 @@\n+x = 1\n",
            }
        ]
    )
    diff = client.get_pr_diff("test/repo", 1)
    assert "diff --git a/src/module.F90 b/src/module.F90" in diff
    assert "+x = 1" in diff


@respx.mock
def test_github_client_rate_limit_error() -> None:
    client = GitHubClient(token=None)
    respx.get("https://api.github.com/repos/test/repo/pulls").respond(
        status_code=403,
        json={"message": "API rate limit exceeded"},
    )
    with pytest.raises(GitHubApiError) as exc_info:
        client.get_pull_requests("test/repo")
    assert "rate limit" in str(exc_info.value).lower()


@respx.mock
def test_sync_repository_end_to_end(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()

    client = GitHubClient(token="mock_token")

    # Mock PRs
    respx.get("https://api.github.com/repos/ufs-community/CATChem/pulls").respond(
        json=[
            {
                "number": 10,
                "title": "Add aerosol scheme",
                "user": {"login": "author_user"},
                "state": "open",
                "base": {"sha": "b1"},
                "head": {"sha": "h1"},
                "created_at": "2026-10-01T12:00:00Z",
                "updated_at": "2026-10-02T12:00:00Z",
                "merged_at": None,
            }
        ]
    )

    # Mock comments
    respx.get(
        "https://api.github.com/repos/ufs-community/CATChem/pulls/10/comments"
    ).respond(
        json=[
            {
                "id": 999,
                "node_id": "PRRC_999",
                "user": {"login": "reviewer_user"},
                "author_association": "MEMBER",
                "body": "Missing molecular weight normalization in ppm to kg/kg conversion",
                "path": "chem/aerosol.F90",
                "line": 45,
                "original_line": 45,
                "start_line": None,
                "side": "RIGHT",
                "diff_hunk": "@@ -40,10 +40,10 @@",
                "created_at": "2026-10-01T14:00:00Z",
                "updated_at": "2026-10-01T14:00:00Z",
            }
        ]
    )

    # Mock commits for diff follow-up tracking
    respx.get(
        "https://api.github.com/repos/ufs-community/CATChem/pulls/10/commits"
    ).respond(
        json=[
            {
                "sha": "c2",
                "commit": {"committer": {"date": "2026-10-02T10:00:00Z"}},
            }
        ]
    )
    respx.get("https://api.github.com/repos/ufs-community/CATChem/commits/c2").respond(
        json={
            "files": [
                {
                    "filename": "chem/aerosol.F90",
                    "patch": "@@ -40,10 +40,12 @@\n+   mw_ratio = mw_spec / 28.964\n",
                }
            ]
        }
    )

    synced_count = sync_repository(
        client=client,
        db=db,
        repo_name="ufs-community/CATChem",
        repo_url="https://github.com/ufs-community/CATChem",
        default_branch="develop",
    )
    assert synced_count == 1

    comments = db.get_review_comments_for_pr("ufs-community/CATChem", 10)
    assert len(comments) == 1
    assert comments[0].comment_node_id == "PRRC_999"
    assert comments[0].has_diff_followup is True


@respx.mock
def test_github_client_forbidden_error() -> None:
    client = GitHubClient(token=None)
    respx.get("https://api.github.com/repos/test/repo/pulls").respond(
        status_code=403,
        text="Resource access restricted",
    )
    with pytest.raises(GitHubApiError) as exc_info:
        client.get_pull_requests("test/repo")
    assert "Forbidden (403)" in str(exc_info.value)
    client.close()


@respx.mock
def test_github_client_server_error() -> None:
    client = GitHubClient(token=None)
    respx.get("https://api.github.com/repos/test/repo/pulls").respond(
        status_code=500,
        text="Internal Server Error",
    )
    with pytest.raises(GitHubApiError) as exc_info:
        client.get_pull_requests("test/repo")
    assert "GitHub API error 500" in str(exc_info.value)
    client.close()


def test_parse_patch_lines_deletions_and_context() -> None:
    from ufs_chem_pr_review_mcp.ingest.syncer import _parse_patch_lines

    patch = "@@ -10,5 +10,6 @@\n context_line\n-deleted_line\n+added_line\n"
    added, deleted = _parse_patch_lines(patch)
    assert added == [11]
    assert deleted == [11]


@respx.mock
def test_sync_repository_no_comments(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    client = GitHubClient(token="mock_token")

    respx.get("https://api.github.com/repos/test/repo/pulls").respond(
        json=[
            {
                "number": 1,
                "title": "Clean PR",
                "user": {"login": "dev"},
                "state": "open",
                "base": {"sha": "b1"},
                "head": {"sha": "h1"},
                "created_at": "2026-10-01T00:00:00Z",
                "updated_at": "2026-10-01T00:00:00Z",
                "merged_at": None,
            }
        ]
    )
    respx.get("https://api.github.com/repos/test/repo/pulls/1/comments").respond(
        json=[]
    )

    synced = sync_repository(client, db, "test/repo", "https://github.com/test/repo")
    assert synced == 0


@respx.mock
def test_sync_repository_commit_detail_failure(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    client = GitHubClient(token="mock_token")

    respx.get("https://api.github.com/repos/test/repo/pulls").respond(
        json=[
            {
                "number": 5,
                "title": "PR with broken commit lookup",
                "user": {"login": "dev"},
                "state": "open",
                "base": {"sha": "b1"},
                "head": {"sha": "h1"},
                "created_at": "2026-10-01T10:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
                "merged_at": None,
            }
        ]
    )
    respx.get("https://api.github.com/repos/test/repo/pulls/5/comments").respond(
        json=[
            {
                "id": 101,
                "node_id": "C101",
                "user": {"login": "rev"},
                "author_association": "MEMBER",
                "body": "Fix this",
                "path": "file.py",
                "line": 5,
                "created_at": "2026-10-01T11:00:00Z",
                "updated_at": "2026-10-01T11:00:00Z",
            }
        ]
    )
    respx.get("https://api.github.com/repos/test/repo/pulls/5/commits").respond(
        json=[
            {
                "sha": "failsha",
                "commit": {"author": {"date": "2026-10-01T12:00:00Z"}},
            }
        ]
    )
    # Commit detail endpoint returns 500 error
    respx.get("https://api.github.com/repos/test/repo/commits/failsha").respond(
        status_code=500,
        text="Commit error",
    )

    synced = sync_repository(client, db, "test/repo", "https://github.com/test/repo")
    assert synced == 1


def test_resolve_github_token_explicit() -> None:
    assert resolve_github_token("explicit_tok") == "explicit_tok"
    assert resolve_github_token("   spaced_tok   ") == "spaced_tok"


def test_resolve_github_token_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UFS_CHEM_GITHUB_TOKEN", "ufs_token")
    monkeypatch.setenv("GITHUB_TOKEN", "gh_token")
    assert resolve_github_token() == "ufs_token"

    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "gh_token")
    assert resolve_github_token() == "gh_token"


def test_resolve_github_token_gh_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    monkeypatch.setattr(
        "shutil.which", lambda cmd: "/usr/local/bin/gh" if cmd == "gh" else None
    )

    class MockCompletedProcess:
        returncode = 0
        stdout = "gh_token_123\n"
        stderr = ""

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockCompletedProcess(),
    )
    assert resolve_github_token() == "gh_token_123"


def test_resolve_github_token_gh_cli_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/gh")

    class MockFailedProcess:
        returncode = 1
        stdout = ""
        stderr = "not logged in"

    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: MockFailedProcess(),
    )
    assert resolve_github_token() is None


def test_resolve_github_token_gh_cli_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/gh")

    def mock_raise(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="gh", timeout=5.0)

    monkeypatch.setattr("subprocess.run", mock_raise)
    assert resolve_github_token() is None


def test_resolve_github_token_no_gh_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UFS_CHEM_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    assert resolve_github_token() is None
