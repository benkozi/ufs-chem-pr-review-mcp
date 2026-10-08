"""Unit tests for Pydantic models in models/."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ufs_chem_pr_review_mcp.models.common import (
    DiffFollowUpStatus,
    OutputFormat,
    ReviewCategory,
    ReviewEvent,
    ReviewMode,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.models.github import (
    GitHubInlineComment,
    GitHubReviewPayload,
)
from ufs_chem_pr_review_mcp.models.mcp_tools import (
    DomainFinding,
    EvaluateDiffInput,
    EvaluatePrInput,
    GeneratePatchInput,
    PonytailFinding,
    ReviewContextResponse,
)
from ufs_chem_pr_review_mcp.models.patch import CodePatch, PatchResult
from ufs_chem_pr_review_mcp.models.review import (
    PullRequestRecord,
    ReviewCommentRecord,
)


def test_enums_values() -> None:
    assert SupportedLanguage.FORTRAN == "fortran"
    assert ReviewCategory.OVERENGINEERING == "overengineering"
    assert DiffFollowUpStatus.CODE_MODIFIED == "code_modified"
    assert OutputFormat.PATCH == "patch"
    assert OutputFormat.ALL == "all"
    assert ReviewMode.SUMMARY_AND_INLINE == "summary_and_inline"
    assert ReviewEvent.REQUEST_CHANGES == "REQUEST_CHANGES"


def test_code_patch_valid() -> None:
    patch = CodePatch(
        file_path="src/chem.F90",
        start_line=10,
        end_line=12,
        original_code="allocate(arr(10))\n",
        replacement_code="allocate(arr(10), stat=rc, errmsg=msg)\n",
        unified_hunk="@@ -10,3 +10,3 @@\n-allocate(arr(10))\n+allocate(arr(10), stat=rc, errmsg=msg)\n",
    )
    assert patch.start_line == 10
    assert patch.file_path == "src/chem.F90"


def test_code_patch_immutability_and_forbid_extra() -> None:
    patch = CodePatch(
        file_path="src/chem.F90",
        start_line=1,
        end_line=1,
        original_code="x = 1\n",
        replacement_code="x = 2\n",
        unified_hunk="@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n",
    )
    with pytest.raises(ValidationError):
        patch.start_line = 5  # type: ignore[misc]

    with pytest.raises(ValidationError):
        CodePatch(
            file_path="src/chem.F90",
            start_line=1,
            end_line=1,
            original_code="x = 1\n",
            replacement_code="x = 2\n",
            unified_hunk="",
            extra_field="disallowed",  # type: ignore[call-arg]
        )


def test_patch_result() -> None:
    res = PatchResult(
        patch_text="diff --git ...",
        files_changed=["a.py"],
        total_additions=1,
        total_deletions=0,
    )
    assert res.files_changed == ["a.py"]
    assert res.total_additions == 1


def test_review_comment_record_validation() -> None:
    now = datetime.now(timezone.utc)
    rec = ReviewCommentRecord(
        id=1,
        comment_node_id="PRRC_kwDO123",
        repo_name="ufs-community/CATChem",
        pr_number=42,
        author_login="reviewer1",
        author_association="MEMBER",
        body="Missing molecular weight normalization",
        path="chem/reactions.F90",
        line=100,
        original_line=100,
        start_line=None,
        side="RIGHT",
        diff_hunk="@@ -95,8 +95,8 @@",
        language=SupportedLanguage.FORTRAN,
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        criticality=5,
        has_diff_followup=True,
        diff_followup_status=DiffFollowUpStatus.CODE_MODIFIED,
        match_score=85.5,
        created_at=now,
        updated_at=now,
        indexed_at=now,
    )
    assert rec.criticality == 5
    assert rec.language == SupportedLanguage.FORTRAN
    assert rec.match_score == 85.5


def test_review_comment_criticality_bounds() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        ReviewCommentRecord(
            id=1,
            comment_node_id="PRRC_1",
            repo_name="repo",
            pr_number=1,
            author_login="user",
            author_association="NONE",
            body="test",
            path="test.py",
            line=1,
            original_line=1,
            start_line=None,
            side="RIGHT",
            diff_hunk=None,
            language=SupportedLanguage.PYTHON,
            category=ReviewCategory.STYLE_DOCS,
            criticality=6,  # Out of bounds > 5
            has_diff_followup=False,
            diff_followup_status=DiffFollowUpStatus.NO_RESPONSE,
            match_score=None,
            created_at=now,
            updated_at=now,
            indexed_at=now,
        )


def test_pull_request_record() -> None:
    now = datetime.now(timezone.utc)
    pr = PullRequestRecord(
        id=10,
        repo_name="ufs-community/CATChem",
        pr_number=99,
        title="Add SOA scheme",
        author_login="author1",
        state="open",
        created_at=now,
        updated_at=now,
        merged_at=None,
        base_sha="abcdef1",
        head_sha="1234567",
        indexed_at=now,
    )
    assert pr.pr_number == 99
    assert pr.merged_at is None


def test_evaluate_pr_input_bounds() -> None:
    inp = EvaluatePrInput(
        repo="ufs-community/CATChem",
        pr_number=10,
        output_format=OutputFormat.PATCH,
        review_mode=ReviewMode.SUMMARY_ONLY,
    )
    assert inp.max_context_comments == 15
    assert inp.output_format == OutputFormat.PATCH

    with pytest.raises(ValidationError):
        EvaluatePrInput(
            repo="repo",
            pr_number=0,  # ge=1 violated
        )


def test_evaluate_diff_input() -> None:
    inp = EvaluateDiffInput(
        diff_text="diff --git a/file b/file\n...",
        target_repo="ufs-community/CATChem",
    )
    assert inp.output_format == OutputFormat.MARKDOWN
    assert inp.review_mode == ReviewMode.SUMMARY_AND_INLINE


def test_findings_and_review_context_response() -> None:
    patch = CodePatch(
        file_path="src/module.F90",
        start_line=5,
        end_line=5,
        original_code="1.0",
        replacement_code="1.0_rk",
        unified_hunk="@@ -5,1 +5,1 @@\n-1.0\n+1.0_rk\n",
    )
    pt_finding = PonytailFinding(
        file_path="src/module.F90",
        line_number=10,
        tag="delete",
        what_to_cut="unused module import",
        replacement="remove line",
        lines_saved_estimate=1,
        original_code="use unused_mod\n",
        replacement_code="",
        patch=None,
    )
    dom_finding = DomainFinding(
        file_path="src/module.F90",
        line_number=5,
        rule_name="single_precision_literal",
        category=ReviewCategory.CHEMISTRY_PHYSICS,
        criticality=4,
        explanation="Use 1.0_rk instead of 1.0",
        original_code="1.0",
        replacement_code="1.0_rk",
        patch=patch,
    )
    resp = ReviewContextResponse(
        repo="ufs-community/CATChem",
        pr_number=12,
        review_mode=ReviewMode.SUMMARY_AND_INLINE,
        touched_files=["src/module.F90"],
        detected_languages=[SupportedLanguage.FORTRAN],
        historical_matches=[],
        ponytail_findings=[pt_finding],
        domain_findings=[dom_finding],
        suggested_patches=[patch],
        diff_text="diff text",
        critical_summary_prompt="Prompt...",
    )
    assert len(resp.ponytail_findings) == 1
    assert len(resp.domain_findings) == 1
    assert len(resp.suggested_patches) == 1


def test_github_payload_models() -> None:
    comment = GitHubInlineComment(
        path="src/file.F90",
        line=25,
        side="RIGHT",
        body="Consider replacing with double precision constant.",
        suggested_change="1.0_rk",
    )
    payload = GitHubReviewPayload(
        event=ReviewEvent.COMMENT,
        body="Critical Summary...",
        comments=[comment],
    )
    assert payload.comments[0].suggested_change == "1.0_rk"
    assert payload.event == ReviewEvent.COMMENT


def test_github_inline_comment_rendered_body() -> None:
    c1 = GitHubInlineComment(
        path="src/file.F90",
        line=10,
        side="RIGHT",
        body="Use double precision.",
        suggested_change="x = 1.0_rk",
    )
    rendered = c1.rendered_body()
    assert "Use double precision." in rendered
    assert "```suggestion\nx = 1.0_rk\n```" in rendered

    c2 = GitHubInlineComment(
        path="src/file.F90",
        line=10,
        side="RIGHT",
        body="Pure comment.",
        suggested_change=None,
    )
    assert c2.rendered_body() == "Pure comment."

    c3 = GitHubInlineComment(
        path="src/file.F90",
        line=10,
        side="RIGHT",
        body="",
        suggested_change="x = 1.0_rk",
    )
    assert c3.rendered_body() == "```suggestion\nx = 1.0_rk\n```"


def test_generate_patch_input() -> None:
    inp = GeneratePatchInput(patches=[])
    assert inp.patches == []
