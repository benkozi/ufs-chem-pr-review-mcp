"""Unit tests for GitHub PR URL parsing."""

import pytest

from ufs_chem_pr_review_mcp.models.github import (
    PrUrlComponents,
    parse_github_pr_url,
)


def test_parse_standard_pr_url() -> None:
    url = "https://github.com/ufs-community/CATChem/pull/123"
    components = parse_github_pr_url(url)
    assert components == PrUrlComponents(
        owner="ufs-community",
        repo="CATChem",
        pr_number=123,
    )
    assert components.full_repo == "ufs-community/CATChem"


def test_parse_pr_url_with_trailing_slash() -> None:
    url = "https://github.com/ufs-community/CATChem/pull/42/"
    components = parse_github_pr_url(url)
    assert components.owner == "ufs-community"
    assert components.repo == "CATChem"
    assert components.pr_number == 42


def test_parse_pr_url_with_files_or_commits_suffix() -> None:
    url_files = "https://github.com/ufs-community/CATChem/pull/99/files"
    assert parse_github_pr_url(url_files).pr_number == 99

    url_commits = "https://github.com/ufs-community/CATChem/pull/99/commits"
    assert parse_github_pr_url(url_commits).pr_number == 99


def test_parse_shorthand_pr_strings() -> None:
    assert parse_github_pr_url("ufs-community/CATChem#55") == PrUrlComponents(
        owner="ufs-community", repo="CATChem", pr_number=55
    )
    assert parse_github_pr_url("ufs-community/CATChem/pull/55") == PrUrlComponents(
        owner="ufs-community", repo="CATChem", pr_number=55
    )


def test_parse_invalid_pr_urls() -> None:
    with pytest.raises(ValueError, match="PR number must be >= 1"):
        parse_github_pr_url("https://github.com/ufs-community/CATChem/pull/0")

    with pytest.raises(ValueError, match="Cannot parse GitHub PR URL"):
        parse_github_pr_url("https://github.com/ufs-community/CATChem")

    with pytest.raises(ValueError, match="Cannot parse GitHub PR URL"):
        parse_github_pr_url("https://github.com/ufs-community/CATChem/issues/123")

    with pytest.raises(ValueError, match="Cannot parse GitHub PR URL"):
        parse_github_pr_url("not-a-valid-url")
