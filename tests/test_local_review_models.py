"""Unit tests for local review comments models and markdown parser."""

import pytest
from pydantic import ValidationError

from ufs_chem_pr_review_mcp.models.common import ReviewCategory, SupportedLanguage
from ufs_chem_pr_review_mcp.models.local_review import (
    FindingSeverity,
    LocalReviewCommentInput,
    ReconciliationStats,
    RecordedCommentSummary,
    RecordReviewCommentsInput,
    RecordReviewCommentsResponse,
    build_pending_review_payload,
    generate_synthetic_node_id,
    get_mcp_server_commit_hash,
    parse_diff_right_ranges,
    parse_review_markdown_findings,
)


def test_finding_severity_properties() -> None:
    assert FindingSeverity.P0_BLOCKER.label == "Blocker"
    assert FindingSeverity.P0_BLOCKER.default_criticality == 5

    assert FindingSeverity.P1_MAJOR.label == "Major"
    assert FindingSeverity.P1_MAJOR.default_criticality == 4

    assert FindingSeverity.P2_MODERATE.label == "Moderate"
    assert FindingSeverity.P2_MODERATE.default_criticality == 3

    assert FindingSeverity.P3_MINOR.label == "Minor"
    assert FindingSeverity.P3_MINOR.default_criticality == 1


def test_local_review_comment_input_defaults() -> None:
    c = LocalReviewCommentInput(
        path="chem/rates.F90",
        line=42,
        body="Missing molecular weight factor in rate expression",
    )
    assert c.path == "chem/rates.F90"
    assert c.line == 42
    assert c.category == ReviewCategory.CORRECTNESS
    assert c.severity == FindingSeverity.P2_MODERATE
    assert c.criticality is None
    assert c.resolved_criticality() == 3
    assert c.author_login == "antigravity-review"


def test_local_review_comment_input_explicit_criticality() -> None:
    c = LocalReviewCommentInput(
        path="chem/rates.F90",
        line=42,
        body="Missing molecular weight factor",
        severity=FindingSeverity.P0_BLOCKER,
        criticality=5,
    )
    assert c.resolved_criticality() == 5


def test_record_review_comments_input_validation() -> None:
    # Missing repo and pr_url
    with pytest.raises(
        ValidationError, match="Must provide either pr_url or both repo and pr_number"
    ):
        RecordReviewCommentsInput(
            comments=[LocalReviewCommentInput(path="a.F90", body="issue")]
        )

    # Missing comment source
    with pytest.raises(
        ValidationError,
        match="Must provide at least one of: comments, review_file_path, or markdown_text",
    ):
        RecordReviewCommentsInput(repo="owner/repo", pr_number=1)

    # Valid with pr_url and comments
    inp = RecordReviewCommentsInput(
        pr_url="https://github.com/ufs-community/CATChem/pull/123",
        comments=[LocalReviewCommentInput(path="a.F90", body="issue")],
    )
    assert inp.pr_url == "https://github.com/ufs-community/CATChem/pull/123"
    assert len(inp.comments) == 1

    # Valid with repo, pr_number, and review_file_path
    inp2 = RecordReviewCommentsInput(
        repo="ufs-community/CATChem",
        pr_number=123,
        review_file_path="reviews/pr-123.md",
    )
    assert inp2.repo == "ufs-community/CATChem"
    assert inp2.pr_number == 123


def test_recorded_comment_summary_and_response() -> None:
    summary = RecordedCommentSummary(
        comment_node_id="local-review:owner/repo#123:a.F90:10:abcdef123456",
        path="a.F90",
        line=10,
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        severity=FindingSeverity.P0_BLOCKER,
        priority_label="Blocker",
        criticality=5,
        status="inserted",
    )
    assert summary.priority_label == "Blocker"
    assert summary.criticality == 5

    resp = RecordReviewCommentsResponse(
        repo="owner/repo",
        pr_number=123,
        total_received=1,
        inserted_count=1,
        updated_count=0,
        db_path="data/ufs_chem_reviews.sqlite3",
        recorded_comments=[summary],
    )
    assert resp.total_received == 1
    assert resp.inserted_count == 1
    assert resp.recorded_comments[0].comment_node_id.startswith("local-review:")


def test_reconciliation_stats() -> None:
    stats = ReconciliationStats(
        repo="owner/repo",
        pr_number=123,
        local_comments_found=3,
        reconciled_count=2,
        retained_local_count=1,
    )
    assert stats.local_comments_found == 3
    assert stats.reconciled_count == 2
    assert stats.retained_local_count == 1


def test_generate_synthetic_node_id() -> None:
    id1 = generate_synthetic_node_id(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        path="chem/rates.F90",
        line=42,
        category="chemistry_physics",
        body="Missing factor",
    )
    # Identical parameters yield identical ID
    id2 = generate_synthetic_node_id(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        path="chem/rates.F90",
        line=42,
        category="chemistry_physics",
        body="Missing factor",
    )
    assert id1 == id2
    assert id1.startswith("local-review:ufs-community/CATChem#123:chem/rates.F90:42:")

    # Different body yields distinct ID
    id3 = generate_synthetic_node_id(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        path="chem/rates.F90",
        line=42,
        category="chemistry_physics",
        body="Different issue",
    )
    assert id1 != id3

    # None line uses '0'
    id_no_line = generate_synthetic_node_id(
        repo_name="ufs-community/CATChem",
        pr_number=123,
        path="chem/rates.F90",
        line=None,
        category="chemistry_physics",
        body="Different issue",
    )
    assert ":0:" in id_no_line


def test_parse_review_markdown_findings() -> None:
    sample_report = """# Pull Request Review: [ufs-community/CATChem#123]

## 4. Prioritized Action Items
- [ ] **[P0]** Numerical Instability in Rates — [chem/rates.F90:42](file:///chem/rates.F90#L42)
- [ ] **[P1]** Unchecked allocate status — [chem/driver.F90:110](file:///chem/driver.F90#L110)
- [ ] **[P2]** Ponytail Dead Code — [chem/utils.F90:15](file:///chem/utils.F90#L15)
- [ ] **[P3]** Typo in comment — [chem/init.F90:5](file:///chem/init.F90#L5)

## 5. Detailed Findings & Machine-Applicable Suggestions

### [P0] Numerical Instability in Rates
- **Location**: [chem/rates.F90:42](file:///path/to/chem/rates.F90#L42)
- **Problem**: Missing molecular weight scaling factor in chemistry photolysis rate.
- **Rationale**: Atmospheric chemistry conservation requires scaling.
- **1-Click Suggestion**:
```suggestion
rate = 1.0_rk * temp * mw_scale
```

### [P1] Missing Allocation Status Check
- **Location**: [chem/driver.F90:110](file:///path/to/chem/driver.F90#L110)
- **Problem**: Memory allocation without stat=rc or errmsg.
- **Rationale**: NOAA OMD standards require allocate checks.

### [P2] Ponytail Over-Engineering: Delete Redundant Wrapper
- **Location**: [chem/utils.F90:15](file:///path/to/chem/utils.F90#L15)
- **Problem**: Wrapper function with single caller.
- **Rationale**: YAGNI simplification.

### [P3] Typo in initialization log
- **Location**: [chem/init.F90:5](file:///path/to/chem/init.F90#L5)
- **Problem**: Misleading log message.
"""

    findings = parse_review_markdown_findings(sample_report)
    assert len(findings) == 4

    p0 = findings[0]
    assert p0.severity == FindingSeverity.P0_BLOCKER
    assert p0.path == "chem/rates.F90"
    assert p0.line == 42
    assert p0.category == ReviewCategory.CHEMISTRY_PHYSICS
    assert p0.language == SupportedLanguage.FORTRAN
    assert p0.suggested_change == "rate = 1.0_rk * temp * mw_scale"
    assert "**[P0 - Blocker] Numerical Instability in Rates**" in p0.body

    p1 = findings[1]
    assert p1.severity == FindingSeverity.P1_MAJOR
    assert p1.path == "chem/driver.F90"
    assert p1.line == 110
    assert p1.category == ReviewCategory.CORRECTNESS
    assert "**[P1 - Major]" in p1.body

    p2 = findings[2]
    assert p2.severity == FindingSeverity.P2_MODERATE
    assert p2.path == "chem/utils.F90"
    assert p2.line == 15
    assert p2.category == ReviewCategory.OVERENGINEERING
    assert "**[P2 - Moderate]" in p2.body

    p3 = findings[3]
    assert p3.severity == FindingSeverity.P3_MINOR
    assert p3.path == "chem/init.F90"
    assert p3.line == 5
    assert (
        p3.category == ReviewCategory.STYLE_DOCS
        or p3.category == ReviewCategory.CORRECTNESS
    )
    assert "**[P3 - Minor]" in p3.body


def test_parse_review_markdown_additional_branches() -> None:
    # Test path with leading slash, ESMF_NUOPC category, and fallback category
    report = """### [P1] NUOPC FieldBundle State Leaking
- **Location**: [/nuopc/cap.F90:80](file:///nuopc/cap.F90#L80)
- **Problem**: State object not cleanly finalized across grid timesteps.
- **Rationale**: ESMF NUOPC compliance.

### [P3] Generic Observation
- **Location**: [notes.txt:1](file:///notes.txt#L1)
- **Problem**: Uncategorized note without known domain triggers.
- **Rationale**: General remark.
"""
    findings = parse_review_markdown_findings(report)
    assert len(findings) == 2
    assert findings[0].path == "nuopc/cap.F90"
    assert findings[0].category == ReviewCategory.ESMF_NUOPC
    assert findings[1].category == ReviewCategory.CORRECTNESS


def test_parse_review_markdown_ranges_and_build_pending_payload() -> None:
    report = """### [P0] Range Finding With Recommended Post Location
- **Location**: `src/mod.cpp:10-30`
- **Recommended Post Location**: `src/mod.cpp:12-18`
- **Tag**: `[memory-safety]`

**[P0]: Range issue**

Fix this range.
```suggestion
int x = 0;
```
---

### [P2] Unanchored General Finding
No location bullet here.
"""
    findings = parse_review_markdown_findings(report)
    assert len(findings) == 2
    assert findings[0].path == "src/mod.cpp"
    assert findings[0].start_line == 12
    assert findings[0].line == 18
    assert "- **Recommended Post Location**:" not in findings[0].body
    assert not findings[0].body.endswith("---")
    assert findings[1].path == "unknown"
    assert findings[1].line is None

    # Test build_pending_review_payload without diff_text
    payload_no_diff = build_pending_review_payload(findings, commit_id="abc1234")
    raw_no_diff = payload_no_diff.to_gh_api_json()
    assert '"event"' not in raw_no_diff
    assert len(payload_no_diff.comments) == 1
    assert payload_no_diff.comments[0].start_line == 12
    assert payload_no_diff.comments[0].line == 18
    assert "File-Level & Out-of-Diff Findings" in payload_no_diff.body

    # Test build_pending_review_payload with diff_text filtering
    diff_text = """diff --git a/src/mod.cpp b/src/mod.cpp
--- a/src/mod.cpp
+++ b/src/mod.cpp
@@ -10,10 +10,12 @@
+int a = 1;
diff --git a/src/other.cpp b/src/other.cpp
--- a/src/other.cpp
+++ b/src/other.cpp
@@ -50 +50 @@
+int b = 2;
"""
    ranges = parse_diff_right_ranges(diff_text)
    assert ranges["src/mod.cpp"] == [(10, 21)]
    assert ranges["src/other.cpp"] == [(50, 50)]

    extra_comments = [
        *findings,
        # Partial range outside hunk start, but end line inside hunk and no suggestion -> attaches to end line
        LocalReviewCommentInput(
            path="src/mod.cpp",
            start_line=2,
            line=15,
            body="End line is in hunk",
        ),
        # Outside diff hunk completely -> goes to out_of_diff_notes
        LocalReviewCommentInput(
            path="src/mod.cpp",
            start_line=100,
            line=105,
            body="Outside diff hunk",
        ),
    ]
    payload_with_diff = build_pending_review_payload(
        extra_comments, diff_text=diff_text
    )
    assert len(payload_with_diff.comments) == 2
    assert payload_with_diff.comments[0].start_line == 12
    assert payload_with_diff.comments[0].line == 18
    assert payload_with_diff.comments[1].start_line is None
    assert payload_with_diff.comments[1].line == 15
    assert "`src/mod.cpp:100-105`" in payload_with_diff.body


def test_get_mcp_server_commit_hash_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def mock_run_nonzero(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git"], returncode=1, stdout="", stderr="err"
        )

    monkeypatch.setattr(subprocess, "run", mock_run_nonzero)
    assert get_mcp_server_commit_hash() == "unknown"

    def mock_run_error(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", mock_run_error)
    assert get_mcp_server_commit_hash() == "unknown"
