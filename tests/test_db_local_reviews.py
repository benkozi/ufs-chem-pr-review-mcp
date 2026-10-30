"""Integration tests for local review comments database recording and sync reconciliation."""

from pathlib import Path

import pytest

from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase, _is_comment_text_match
from ufs_chem_pr_review_mcp.models.common import ReviewCategory
from ufs_chem_pr_review_mcp.models.local_review import (
    FindingSeverity,
    LocalReviewCommentInput,
)


@pytest.fixture
def test_db(tmp_path: Path) -> ReviewDatabase:
    db_file = tmp_path / "test_reviews.sqlite3"
    db = ReviewDatabase(db_file)
    db.init_schema()
    return db


def test_is_comment_text_match() -> None:
    assert not _is_comment_text_match("", "content")
    assert not _is_comment_text_match("content", "")

    # Exact match
    assert _is_comment_text_match("Exact match body", "Exact match body")

    # Substring inclusion
    assert _is_comment_text_match(
        "Missing molecular weight factor",
        "**[P0 - Blocker] Missing molecular weight factor in photolysis rate**\n\nPlease add mw_scale.",
    )

    # Substantial word overlap
    local = "Please add stat=rc and errmsg=msg error checks to Fortran allocate calls."
    gh = "Fortran allocate calls must include stat=rc and errmsg=msg error handling."
    assert _is_comment_text_match(local, gh)

    # Completely different comments
    diff1 = "Formatting typo on script line"
    diff2 = "Uninitialized pointer in CUDA kernel solver"
    assert not _is_comment_text_match(diff1, diff2)


def test_record_local_review_comments_new_repo_and_pr(test_db: ReviewDatabase) -> None:
    comments = [
        LocalReviewCommentInput(
            path="chem/rates.F90",
            line=42,
            body="Missing molecular weight factor",
            category=ReviewCategory.CHEMISTRY_PHYSICS,
            severity=FindingSeverity.P0_BLOCKER,
            suggested_change="rate = 1.0_rk * temp * mw_scale",
        ),
        LocalReviewCommentInput(
            path="chem/driver.F90",
            line=110,
            body="Allocate missing stat=rc check",
            category=ReviewCategory.CORRECTNESS,
            severity=FindingSeverity.P1_MAJOR,
        ),
    ]

    inserted, updated, summaries = test_db.record_local_review_comments(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        comments=comments,
        pr_title="Add new photolysis chemistry scheme",
    )

    assert inserted == 2
    assert updated == 0
    assert len(summaries) == 2
    assert summaries[0].priority_label == "Blocker"
    assert summaries[0].criticality == 5
    assert summaries[1].priority_label == "Major"
    assert summaries[1].criticality == 4

    # Verify repository was created
    repo = test_db.get_repository("ufs-community/CATChem")
    assert repo is not None
    assert repo["name"] == "ufs-community/CATChem"

    # Verify pull request was created
    pr = test_db.get_pull_request("ufs-community/CATChem", 123)
    assert pr is not None
    assert pr.title == "Add new photolysis chemistry scheme"

    # Verify review comments stored
    db_comments = test_db.get_review_comments_for_pr("ufs-community/CATChem", 123)
    assert len(db_comments) == 2
    assert any("mw_scale" in c.body for c in db_comments)

    # Verify FTS5 search works immediately
    fts_results = test_db.search_review_comments(
        "molecular weight", repo="ufs-community/CATChem"
    )
    assert len(fts_results) == 1
    assert fts_results[0].line == 42


def test_record_local_review_comments_idempotent_update(
    test_db: ReviewDatabase,
) -> None:
    comments = [
        LocalReviewCommentInput(
            path="chem/rates.F90",
            line=42,
            body="Initial comment body",
            category=ReviewCategory.CHEMISTRY_PHYSICS,
            severity=FindingSeverity.P0_BLOCKER,
        ),
    ]

    # First insertion
    ins1, upd1, _ = test_db.record_local_review_comments(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        comments=comments,
    )
    assert ins1 == 1
    assert upd1 == 0

    # Re-running with same body produces update on identical synthetic node ID
    ins2, upd2, summaries2 = test_db.record_local_review_comments(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        comments=comments,
    )
    assert ins2 == 0
    assert upd2 == 1
    assert summaries2[0].status == "updated"

    # Total comments in DB remains 1
    db_comments = test_db.get_review_comments_for_pr("ufs-community/CATChem", 123)
    assert len(db_comments) == 1


def test_reconcile_local_comments_with_incoming_github(test_db: ReviewDatabase) -> None:
    # 1. Record two local review findings
    local_comments = [
        LocalReviewCommentInput(
            path="chem/rates.F90",
            line=42,
            body="Missing molecular weight factor in rate expression",
            category=ReviewCategory.CHEMISTRY_PHYSICS,
            severity=FindingSeverity.P0_BLOCKER,
            suggested_change="rate = 1.0_rk * temp * mw_scale",
        ),
        LocalReviewCommentInput(
            path="chem/driver.F90",
            line=110,
            body="Allocate missing stat=rc check",
            category=ReviewCategory.CORRECTNESS,
            severity=FindingSeverity.P1_MAJOR,
        ),
    ]
    test_db.record_local_review_comments(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        comments=local_comments,
    )

    # Verify both are local
    initial_db = test_db.get_review_comments_for_pr("ufs-community/CATChem", 123)
    assert len(initial_db) == 2

    # 2. Simulate GitHub sync fetching 1 matching comment (user posted rates.F90 comment to PR)
    gh_incoming = [
        {
            "id": 999888,
            "node_id": "PRRC_kwDO_real_github_node",
            "path": "chem/rates.F90",
            "line": 42,
            "body": "Missing molecular weight factor in rate expression\n\n```suggestion\nrate = 1.0_rk * temp * mw_scale\n```",
            "user": {"login": "bkoziol"},
        }
    ]

    stats = test_db.reconcile_local_comments_for_pr(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        incoming_gh_comments=gh_incoming,
    )

    assert stats.local_comments_found == 2
    assert stats.reconciled_count == 1
    assert stats.retained_local_count == 1

    # The rates.F90 local row is deleted; driver.F90 remains
    remaining = test_db.get_review_comments_for_pr("ufs-community/CATChem", 123)
    assert len(remaining) == 1
    assert remaining[0].path == "chem/driver.F90"
    assert remaining[0].comment_node_id.startswith("local-review:")


def test_reconcile_no_local_comments(test_db: ReviewDatabase) -> None:
    stats = test_db.reconcile_local_comments_for_pr(
        repo_name="ufs-community/CATChem",
        pr_number=999,
        incoming_gh_comments=[{"path": "a.F90", "line": 1, "body": "hello"}],
    )
    assert stats.local_comments_found == 0
    assert stats.reconciled_count == 0


def test_reconcile_multiple_incoming_comments_for_same_local(
    test_db: ReviewDatabase,
) -> None:
    test_db.record_local_review_comments(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        comments=[
            LocalReviewCommentInput(
                path="chem/rates.F90",
                line=42,
                body="Missing molecular weight factor in rate expression",
                category=ReviewCategory.CHEMISTRY_PHYSICS,
                severity=FindingSeverity.P0_BLOCKER,
            )
        ],
    )

    # 2 incoming GitHub comments both matching the same local comment
    gh_comments = [
        {
            "path": "chem/rates.F90",
            "line": 42,
            "body": "Missing molecular weight factor in rate expression",
        },
        {
            "path": "chem/rates.F90",
            "line": 42,
            "body": "Missing molecular weight factor in rate expression reply",
        },
    ]
    stats = test_db.reconcile_local_comments_for_pr(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        incoming_gh_comments=gh_comments,
    )
    assert stats.reconciled_count == 1
    assert stats.retained_local_count == 0


def test_is_comment_text_match_no_tokens() -> None:
    # No tokens of length >= 3
    assert not _is_comment_text_match("::", "!!")
    assert not _is_comment_text_match("ab cd", "ef gh")
