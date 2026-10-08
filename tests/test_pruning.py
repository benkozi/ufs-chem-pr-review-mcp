"""Unit tests for database pruning and retention policies."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ufs_chem_pr_review_mcp.db.pruning import prune_database
from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.models.common import (
    DiffFollowUpStatus,
    ReviewCategory,
    SupportedLanguage,
)


def test_prune_database_no_policies(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    conn = sqlite3.connect(tmp_db_path)
    deleted = prune_database(conn, retention_days=None, max_records_per_repo=None)
    assert deleted == 0
    conn.close()


def test_prune_database_retention_days(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()

    old_date = datetime.now(timezone.utc) - timedelta(days=120)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)

    db.upsert_repository("ufs-community/CATChem", "url", "main")
    # Old PR
    db.upsert_pull_request(
        "ufs-community/CATChem",
        1,
        "Old PR",
        "u",
        "closed",
        "b",
        "h",
        old_date,
        old_date,
    )
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="OLD_C",
        author_login="u",
        author_association="NONE",
        body="old comment",
        path="old.F90",
        line=1,
        original_line=1,
        start_line=None,
        side="RIGHT",
        diff_hunk=None,
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.STYLE_DOCS,
        criticality=1,
        has_diff_followup=False,
        diff_followup_status=DiffFollowUpStatus.NO_RESPONSE,
        created_at=old_date,
        updated_at=old_date,
    )

    # Recent PR
    db.upsert_pull_request(
        "ufs-community/CATChem",
        2,
        "Recent PR",
        "u",
        "open",
        "b",
        "h",
        recent_date,
        recent_date,
    )
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=2,
        comment_node_id="RECENT_C",
        author_login="u",
        author_association="NONE",
        body="recent comment",
        path="recent.F90",
        line=1,
        original_line=1,
        start_line=None,
        side="RIGHT",
        diff_hunk=None,
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.STYLE_DOCS,
        criticality=1,
        has_diff_followup=False,
        diff_followup_status=DiffFollowUpStatus.NO_RESPONSE,
        created_at=recent_date,
        updated_at=recent_date,
    )

    conn = sqlite3.connect(tmp_db_path)
    deleted = prune_database(conn, retention_days=90)
    assert deleted == 1

    # Verify old PR is gone and recent PR remains
    assert db.get_pull_request("ufs-community/CATChem", 1) is None
    assert db.get_pull_request("ufs-community/CATChem", 2) is not None
    conn.close()


def test_prune_database_max_records_per_repo(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()

    now = datetime.now(timezone.utc)
    db.upsert_repository("ufs-community/CATChem", "url", "main")

    # Insert 5 PRs
    for i in range(1, 6):
        d = now - timedelta(days=10 - i)
        db.upsert_pull_request(
            "ufs-community/CATChem", i, f"PR {i}", "u", "closed", "b", "h", d, d
        )

    conn = sqlite3.connect(tmp_db_path)
    # Limit to 3 PRs max
    deleted = prune_database(conn, max_records_per_repo=3)
    assert deleted == 2
    # The oldest 2 (PR 1 and PR 2) should be deleted
    assert db.get_pull_request("ufs-community/CATChem", 1) is None
    assert db.get_pull_request("ufs-community/CATChem", 2) is None
    assert db.get_pull_request("ufs-community/CATChem", 5) is not None
    conn.close()
