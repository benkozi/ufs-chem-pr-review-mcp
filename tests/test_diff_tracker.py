"""Unit tests for diff tracking and Fortran continuation normalization."""

from ufs_chem_pr_review_mcp.ingest.diff_tracker import (
    determine_followup_status,
    normalize_fortran_continuations,
)
from ufs_chem_pr_review_mcp.models.common import DiffFollowUpStatus


def test_normalize_fortran_continuations_single_line() -> None:
    lines = ["x = 1.0_rk", "y = 2.0_rk"]
    normalized, mapping = normalize_fortran_continuations(lines)
    assert normalized == lines
    assert mapping == {0: (0, 0), 1: (1, 1)}


def test_normalize_fortran_continuations_ampersand() -> None:
    lines = [
        "call some_subroutine(arg1, &",
        "  arg2, &",
        "  arg3)",
        "x = 5.0",
    ]
    normalized, mapping = normalize_fortran_continuations(lines)
    assert len(normalized) == 2
    assert normalized[0] == "call some_subroutine(arg1,   arg2,   arg3)"
    assert normalized[1] == "x = 5.0"
    assert mapping[0] == (0, 2)
    assert mapping[1] == (3, 3)


def test_determine_followup_status_code_modified() -> None:
    # A subsequent commit touched the file within line window
    commit_patches = [
        {"path": "chem/rates.F90", "added_lines": [10, 11, 12], "deleted_lines": [9]}
    ]
    status, has_followup = determine_followup_status(
        comment_path="chem/rates.F90",
        comment_line=10,
        subsequent_patches=commit_patches,
        thread_resolved=False,
        has_replies=False,
    )
    assert status == DiffFollowUpStatus.CODE_MODIFIED
    assert has_followup is True


def test_determine_followup_status_discussion_only() -> None:
    # No subsequent commits, but author replied
    status, has_followup = determine_followup_status(
        comment_path="chem/rates.F90",
        comment_line=10,
        subsequent_patches=[],
        thread_resolved=False,
        has_replies=True,
    )
    assert status == DiffFollowUpStatus.DISCUSSION_ONLY
    assert has_followup is False


def test_determine_followup_status_resolved_explanation() -> None:
    # Thread was marked resolved without code patch
    status, has_followup = determine_followup_status(
        comment_path="chem/rates.F90",
        comment_line=10,
        subsequent_patches=[],
        thread_resolved=True,
        has_replies=True,
    )
    assert status == DiffFollowUpStatus.REJECTED_EXPLAINED
    assert has_followup is False


def test_determine_followup_status_no_response() -> None:
    # No follow up commits and no replies
    status, has_followup = determine_followup_status(
        comment_path="chem/rates.F90",
        comment_line=10,
        subsequent_patches=[],
        thread_resolved=False,
        has_replies=False,
    )
    assert status == DiffFollowUpStatus.NO_RESPONSE
    assert has_followup is False


def test_normalize_fortran_continuations_trailing_ampersand_eof() -> None:
    lines = [
        "x = 1.0_rk",
        "call some_subroutine(arg1, &",
        "  arg2 &",
    ]
    normalized, mapping = normalize_fortran_continuations(lines)
    assert len(normalized) == 2
    assert normalized[0] == "x = 1.0_rk"
    assert normalized[1] == "call some_subroutine(arg1,   arg2 "
    assert mapping[1] == (1, 2)


def test_determine_followup_status_comment_line_none() -> None:
    commit_patches = [
        {"path": "chem/rates.F90", "added_lines": [10], "deleted_lines": []}
    ]
    status, has_followup = determine_followup_status(
        comment_path="chem/rates.F90",
        comment_line=None,
        subsequent_patches=commit_patches,
    )
    assert status == DiffFollowUpStatus.CODE_MODIFIED
    assert has_followup is True
