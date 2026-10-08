"""Unit tests for SQLite schema, DAL, FTS5 searching, and match_score calculation."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ufs_chem_pr_review_mcp.db.repository import (
    ReviewDatabase,
    compute_match_score,
    sanitize_fts_query,
)
from ufs_chem_pr_review_mcp.db.schema import CURRENT_SCHEMA_VERSION, init_db
from ufs_chem_pr_review_mcp.models.common import (
    DiffFollowUpStatus,
    ReviewCategory,
    SupportedLanguage,
)


def test_sanitize_fts_query() -> None:
    # Operators and code punctuation
    assert (
        sanitize_fts_query('ESMF_StateGet(state, "tracer")')
        == '"ESMF_StateGet" "state" "tracer"'
    )
    assert sanitize_fts_query("x - y + z * w") == '"x" "y" "z" "w"'
    assert sanitize_fts_query("Chem_Init::run()") == '"Chem_Init" "run"'
    assert sanitize_fts_query('unclosed "quote') == '"unclosed" "quote"'
    assert sanitize_fts_query("") == '""'
    assert sanitize_fts_query("   ") == '""'


def test_compute_match_score() -> None:
    # Exact path match + followup + high criticality
    score_exact = compute_match_score(
        comment_path="chem/reactions.F90",
        diff_path="chem/reactions.F90",
        comment_lang=SupportedLanguage.FORTRAN,
        diff_lang=SupportedLanguage.FORTRAN,
        has_diff_followup=True,
        criticality=5,
        bm25_rank=-5.0,
    )
    # Expected: 50.0 (exact) + 20.0 (followup) + 25.0 (5*5) + 10.0 (lang) + rank bonus
    assert score_exact > 100.0

    # Directory match only, no followup, low criticality
    score_dir = compute_match_score(
        comment_path="chem/reactions.F90",
        diff_path="chem/other.F90",
        comment_lang=SupportedLanguage.FORTRAN,
        diff_lang=SupportedLanguage.FORTRAN,
        has_diff_followup=False,
        criticality=1,
        bm25_rank=0.0,
    )
    # Expected: 25.0 (dir) + 0.0 + 5.0 (1*5) + 10.0 (lang) = 40.0
    assert score_dir == 40.0

    # Unrelated path, different language
    score_unrelated = compute_match_score(
        comment_path="docs/index.md",
        diff_path="src/calc.py",
        comment_lang=SupportedLanguage.MARKDOWN,
        diff_lang=SupportedLanguage.PYTHON,
        has_diff_followup=False,
        criticality=2,
        bm25_rank=0.0,
    )
    # Expected: 0.0 + 0.0 + 10.0 (2*5) + 0.0 = 10.0
    assert score_unrelated == 10.0


def test_init_db_and_migration(tmp_db_path: Path) -> None:
    conn = sqlite3.connect(tmp_db_path)
    init_db(conn)

    # Verify user_version
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    version = cursor.fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION

    # Idempotent re-initialization
    init_db(conn)
    cursor.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] == CURRENT_SCHEMA_VERSION
    conn.close()


def test_repository_crud_and_cascade(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()

    # Upsert repo
    repo_id = db.upsert_repository(
        "ufs-community/CATChem", "https://github.com/ufs-community/CATChem", "develop"
    )
    assert repo_id > 0

    repo = db.get_repository("ufs-community/CATChem")
    assert repo is not None
    assert repo["name"] == "ufs-community/CATChem"
    assert repo["default_branch"] == "develop"

    # Upsert PR
    now = datetime.now(timezone.utc)
    pr_id = db.upsert_pull_request(
        repo_name="ufs-community/CATChem",
        pr_number=101,
        title="Fix Photolysis Rate",
        author_login="scientist1",
        state="open",
        base_sha="base123",
        head_sha="head456",
        created_at=now,
        updated_at=now,
        merged_at=None,
    )
    assert pr_id > 0

    pr = db.get_pull_request("ufs-community/CATChem", 101)
    assert pr is not None
    assert pr.title == "Fix Photolysis Rate"

    # Insert comment
    comment_id = db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=101,
        comment_node_id="PRRC_test1",
        author_login="reviewerA",
        author_association="MEMBER",
        body="Missing molecular weight normalization in unit conversion",
        path="chem/reactions.F90",
        line=120,
        original_line=120,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ -115,10 +115,10 @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        criticality=5,
        has_diff_followup=True,
        diff_followup_status=DiffFollowUpStatus.CODE_MODIFIED,
        created_at=now,
        updated_at=now,
    )
    assert comment_id > 0

    comments = db.get_review_comments_for_pr("ufs-community/CATChem", 101)
    assert len(comments) == 1
    assert comments[0].comment_node_id == "PRRC_test1"
    assert comments[0].criticality == 5


def test_fts_search_and_ranking(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()

    now = datetime.now(timezone.utc)
    db.upsert_repository("ufs-community/CATChem", "url", "main")
    db.upsert_pull_request(
        "ufs-community/CATChem", 1, "PR 1", "u", "open", "b", "h", now, now
    )

    # Insert two comments: one on units, one on allocate
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="C1",
        author_login="rev1",
        author_association="COLLABORATOR",
        body="Molecular weight normalization is missing for aerosol conversion",
        path="chem/aerosol.F90",
        line=42,
        original_line=42,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ ... @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        criticality=5,
        has_diff_followup=True,
        diff_followup_status=DiffFollowUpStatus.CODE_MODIFIED,
        created_at=now,
        updated_at=now,
    )
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="C2",
        author_login="rev2",
        author_association="CONTRIBUTOR",
        body="Missing stat= and errmsg= checks in allocate statement",
        path="chem/memory.F90",
        line=10,
        original_line=10,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ ... @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CORRECTNESS,
        criticality=4,
        has_diff_followup=False,
        diff_followup_status=DiffFollowUpStatus.DISCUSSION_ONLY,
        created_at=now,
        updated_at=now,
    )

    # Search for "molecular weight"
    results = db.search_review_comments(query="molecular weight")
    assert len(results) == 1
    assert results[0].comment_node_id == "C1"

    # Search with category filter
    results_cat = db.search_review_comments(
        query="statement", category=ReviewCategory.CORRECTNESS
    )
    assert len(results_cat) == 1
    assert results_cat[0].comment_node_id == "C2"

    # Search with min_criticality
    results_crit = db.search_review_comments(query="F90", min_criticality=5)
    assert len(results_crit) == 1
    assert results_crit[0].comment_node_id == "C1"

    # Search with has_diff_followup_only
    results_followup = db.search_review_comments(
        query="chem", has_diff_followup_only=True
    )
    assert len(results_followup) == 1
    assert results_followup[0].comment_node_id == "C1"

    # Search with repo filter
    results_repo = db.search_review_comments(
        query="molecular", repo="ufs-community/CATChem"
    )
    assert len(results_repo) == 1
    assert results_repo[0].comment_node_id == "C1"

    # Nonexistent PR lookup
    assert db.get_pull_request("ufs-community/CATChem", 999) is None


def test_query_relevant_comments_scored(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    now = datetime.now(timezone.utc)
    db.upsert_repository("ufs-community/CATChem", "url", "main")
    db.upsert_pull_request(
        "ufs-community/CATChem", 1, "PR 1", "u", "open", "b", "h", now, now
    )

    # Insert comment on reactions.F90
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="C1",
        author_login="rev1",
        author_association="MEMBER",
        body="Always check rc error return code from ESMF_StateGet",
        path="chem/reactions.F90",
        line=10,
        original_line=10,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ ... @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.ESMF_NUOPC,
        criticality=4,
        has_diff_followup=True,
        diff_followup_status=DiffFollowUpStatus.CODE_MODIFIED,
        created_at=now,
        updated_at=now,
    )

    # Insert second comment on reactions.F90 without matching identifiers
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="C2",
        author_login="rev2",
        author_association="MEMBER",
        body="Formatting and indentation looks clean",
        path="chem/reactions.F90",
        line=20,
        original_line=20,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ ... @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CORRECTNESS,
        criticality=1,
        has_diff_followup=False,
        diff_followup_status=DiffFollowUpStatus.DISCUSSION_ONLY,
        created_at=now,
        updated_at=now,
    )

    # Query relevant comments for diff touching chem/reactions.F90
    matches = db.query_relevant_comments(
        target_repo="ufs-community/CATChem",
        touched_files=["chem/reactions.F90"],
        languages=[SupportedLanguage.FORTRAN],
        identifiers=["ESMF_StateGet", "rc"],
        limit=5,
    )
    assert len(matches) == 2
    assert matches[0].match_score is not None
    assert matches[0].match_score > 90.0


def test_get_repo_stats(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    now = datetime.now(timezone.utc)
    db.upsert_repository("ufs-community/CATChem", "url", "main")
    db.upsert_pull_request(
        "ufs-community/CATChem", 1, "PR 1", "u", "open", "b", "h", now, now
    )
    db.insert_review_comment(
        repo_name="ufs-community/CATChem",
        pr_number=1,
        comment_node_id="C1",
        author_login="reviewer1",
        author_association="MEMBER",
        body="body",
        path="file.F90",
        line=1,
        original_line=1,
        start_line=None,
        side="RIGHT",
        diff_hunk=None,
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        criticality=5,
        has_diff_followup=True,
        diff_followup_status=DiffFollowUpStatus.CODE_MODIFIED,
        created_at=now,
        updated_at=now,
    )
    stats = db.get_repo_stats("ufs-community/CATChem")
    assert stats["total_prs"] == 1
    assert stats["total_comments"] == 1
    assert stats["diff_followup_count"] == 1
    assert stats["diff_followup_rate"] == 1.0
    assert stats["top_reviewers"] == [{"author_login": "reviewer1", "count": 1}]


def test_db_read_only_and_missing_lookups(tmp_db_path: Path) -> None:
    # Initialize schema first with read_only=False
    init_db = ReviewDatabase(tmp_db_path, read_only=False)
    init_db.init_schema()

    db = ReviewDatabase(tmp_db_path, read_only=True)
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA query_only;")
    assert cursor.fetchone()[0] == 1
    conn.close()

    # Nonexistent repo lookup
    assert db.get_repository("nonexistent/repo") is None


def test_db_unregistered_errors(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    now = datetime.now(timezone.utc)

    # Upsert PR for unregistered repo raises ValueError
    with pytest.raises(ValueError) as exc:
        db.upsert_pull_request(
            "unregistered/repo", 1, "T", "a", "open", "b", "h", now, now
        )
    assert "Repository not registered" in str(exc.value)

    # Insert comment for unregistered PR raises ValueError
    db.upsert_repository("reg/repo", "url")
    with pytest.raises(ValueError) as exc:
        db.insert_review_comment(
            repo_name="reg/repo",
            pr_number=999,
            comment_node_id="C",
            author_login="u",
            author_association="NONE",
            body="b",
            path="p",
            line=1,
            original_line=1,
            start_line=None,
            side="RIGHT",
            diff_hunk=None,
            language=SupportedLanguage.PYTHON,
            category=ReviewCategory.STYLE_DOCS,
            criticality=1,
            has_diff_followup=False,
            diff_followup_status=DiffFollowUpStatus.NO_RESPONSE,
            created_at=now,
            updated_at=now,
        )
    assert "Pull request not registered" in str(exc.value)


def test_db_list_and_update_synced(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    db.upsert_repository("repo/a", "url_a", "main")
    db.upsert_repository("repo/b", "url_b", "develop")
    repos = db.list_repositories()
    assert len(repos) == 2
    assert repos[0]["name"] == "repo/a"

    now = datetime.now(timezone.utc)
    db.update_repo_synced_at("repo/a", now)
    repo_a = db.get_repository("repo/a")
    assert repo_a is not None
    assert repo_a["last_synced_at"] != ""


def test_db_search_with_language_filter_and_empty_query(tmp_db_path: Path) -> None:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    now = datetime.now(timezone.utc)
    db.upsert_repository("test/repo", "url", "main")
    db.upsert_pull_request("test/repo", 1, "Title", "user", "open", "b", "h", now, now)
    db.insert_review_comment(
        repo_name="test/repo",
        pr_number=1,
        comment_node_id="C_PY",
        author_login="user",
        author_association="NONE",
        body="python style comment",
        path="script.py",
        line=5,
        original_line=5,
        start_line=None,
        side="RIGHT",
        diff_hunk=None,
        language=SupportedLanguage.PYTHON,
        category=ReviewCategory.STYLE_DOCS,
        criticality=2,
        has_diff_followup=False,
        diff_followup_status=DiffFollowUpStatus.NO_RESPONSE,
        created_at=now,
        updated_at=now,
    )

    # Search with language filter
    results = db.search_review_comments(
        query="comment", language=SupportedLanguage.PYTHON
    )
    assert len(results) == 1
    assert results[0].language == SupportedLanguage.PYTHON

    # Search with empty query
    empty_results = db.query_relevant_comments(
        target_repo="test/repo",
        touched_files=[],
        languages=[],
        identifiers=None,
    )
    assert isinstance(empty_results, list)
