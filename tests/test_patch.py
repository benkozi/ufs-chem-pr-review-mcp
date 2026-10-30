"""Unit tests for patch utilities and git apply compatibility."""

from ufs_chem_pr_review_mcp.models.patch import (
    CodePatch,
    build_unified_diff_patch,
)


def test_build_unified_diff_patch_empty() -> None:
    result = build_unified_diff_patch([])
    assert result.patch_text == ""
    assert result.files_changed == []
    assert result.total_additions == 0
    assert result.total_deletions == 0


def test_build_unified_diff_patch_single_replacement() -> None:
    patch = CodePatch(
        file_path="src/chem.F90",
        start_line=10,
        end_line=10,
        original_code="allocate(arr(n))\n",
        replacement_code="allocate(arr(n), stat=rc, errmsg=msg)\n",
        unified_hunk="@@ -10,1 +10,1 @@\n-allocate(arr(n))\n+allocate(arr(n), stat=rc, errmsg=msg)\n",
    )
    result = build_unified_diff_patch([patch])
    assert result.files_changed == ["src/chem.F90"]
    assert "--- a/src/chem.F90" in result.patch_text
    assert "+++ b/src/chem.F90" in result.patch_text
    assert "@@ -10,1 +10,1 @@" in result.patch_text
    assert result.total_additions == 1
    assert result.total_deletions == 1


def test_build_unified_diff_patch_descending_line_sort() -> None:
    patch_early = CodePatch(
        file_path="src/chem.F90",
        start_line=5,
        end_line=5,
        original_code="use old_mod\n",
        replacement_code="",
        unified_hunk="@@ -5,1 +5,0 @@\n-use old_mod\n",
    )
    patch_late = CodePatch(
        file_path="src/chem.F90",
        start_line=50,
        end_line=50,
        original_code="x = 1.0\n",
        replacement_code="x = 1.0_rk\n",
        unified_hunk="@@ -50,1 +50,1 @@\n-x = 1.0\n+x = 1.0_rk\n",
    )
    # Pass them in ascending order; output must sort by descending line number
    result = build_unified_diff_patch([patch_early, patch_late])
    pos_late = result.patch_text.find("@@ -50,1 +50,1 @@")
    pos_early = result.patch_text.find("@@ -5,1 +5,0 @@")
    assert pos_late < pos_early
    assert result.total_deletions == 2
    assert result.total_additions == 1


def test_build_unified_diff_patch_multi_file() -> None:
    p1 = CodePatch(
        file_path="file_b.py",
        start_line=1,
        end_line=1,
        original_code="import os\n",
        replacement_code="",
        unified_hunk="@@ -1,1 +1,0 @@\n-import os\n",
    )
    p2 = CodePatch(
        file_path="file_a.py",
        start_line=2,
        end_line=2,
        original_code="import sys\n",
        replacement_code="",
        unified_hunk="@@ -2,1 +2,0 @@\n-import sys\n",
    )
    result = build_unified_diff_patch([p1, p2])
    assert set(result.files_changed) == {"file_a.py", "file_b.py"}
    assert "--- a/file_a.py" in result.patch_text
    assert "--- a/file_b.py" in result.patch_text
