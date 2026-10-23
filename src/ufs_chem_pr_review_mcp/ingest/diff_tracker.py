"""Diff follow-up association and Fortran continuation line normalization."""

from typing import Any

from ufs_chem_pr_review_mcp.models.common import DiffFollowUpStatus


def normalize_fortran_continuations(
    lines: list[str],
) -> tuple[list[str], dict[int, tuple[int, int]]]:
    """Normalize multi-line Fortran statements connected with '&' into single logical lines.

    Returns:
        (normalized_lines, mapping)
        where mapping maps normalized_index -> (start_orig_index, end_orig_index).
    """
    normalized: list[str] = []
    mapping: dict[int, tuple[int, int]] = {}

    current_statement: list[str] = []
    start_idx = 0

    for idx, line in enumerate(lines):
        stripped = line.rstrip()
        if not current_statement:
            start_idx = idx

        if stripped.endswith("&"):
            # Strip trailing ampersand and accumulate
            current_statement.append(stripped[:-1])
        else:
            if current_statement:
                current_statement.append(line)
                norm_idx = len(normalized)
                normalized.append("".join(current_statement))
                mapping[norm_idx] = (start_idx, idx)
                current_statement = []
            else:
                norm_idx = len(normalized)
                normalized.append(line)
                mapping[norm_idx] = (idx, idx)

    if current_statement:
        norm_idx = len(normalized)
        normalized.append("".join(current_statement))
        mapping[norm_idx] = (start_idx, len(lines) - 1)

    return normalized, mapping


def determine_followup_status(
    comment_path: str,
    comment_line: int | None,
    subsequent_patches: list[dict[str, Any]],
    thread_resolved: bool = False,
    has_replies: bool = False,
) -> tuple[DiffFollowUpStatus, bool]:
    """Determine whether subsequent commits addressed the review comment or if it was discussion only.

    Args:
        comment_path: File path referenced by the comment.
        comment_line: Line number referenced in the diff.
        subsequent_patches: List of commit patch dicts touching files after comment creation.
        thread_resolved: Whether the review thread was marked as resolved on GitHub.
        has_replies: Whether the thread has discussion replies.

    Returns:
        (DiffFollowUpStatus, has_diff_followup_bool)
    """
    target_window = 10  # lines +/- 10

    for patch in subsequent_patches:
        if patch.get("path") == comment_path:
            added = patch.get("added_lines", [])
            deleted = patch.get("deleted_lines", [])

            if comment_line is None:
                # Any modification to the file counts if comment lacked line
                return DiffFollowUpStatus.CODE_MODIFIED, True

            # Check if any added or deleted line falls within line window
            all_modified = set(added).union(deleted)
            if any(
                abs(line_no - comment_line) <= target_window for line_no in all_modified
            ):
                return DiffFollowUpStatus.CODE_MODIFIED, True

    if thread_resolved and has_replies:
        return DiffFollowUpStatus.REJECTED_EXPLAINED, False

    if has_replies:
        return DiffFollowUpStatus.DISCUSSION_ONLY, False

    return DiffFollowUpStatus.NO_RESPONSE, False
