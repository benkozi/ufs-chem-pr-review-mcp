"""Unit tests for Ponytail over-engineering heuristic engine."""

from ufs_chem_pr_review_mcp.models.common import SupportedLanguage
from ufs_chem_pr_review_mcp.rules.ponytail import evaluate_ponytail_rules


def test_ponytail_delete_commented_code() -> None:
    diff_hunk = """@@ -1,5 +1,7 @@
 subroutine test()
+  ! x = old_call(1, 2, 3)
+  ! y = 4.0
+  z = 5.0
 end subroutine
"""
    findings = evaluate_ponytail_rules(
        "src/calc.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert len(findings) >= 1
    f = findings[0]
    assert f.tag == "delete"
    assert "commented-out" in f.what_to_cut.lower()
    assert f.original_code is not None
    assert f.replacement_code == ""
    assert f.patch is not None
    assert f.patch.start_line == 2


def test_ponytail_stdlib_reimplementation() -> None:
    diff_hunk = """@@ -10,5 +10,12 @@
+def custom_min(a, b):
+    if a < b:
+        return a
+    return b
"""
    findings = evaluate_ponytail_rules(
        "scripts/util.py", diff_hunk, SupportedLanguage.PYTHON
    )
    assert any(f.tag == "stdlib" for f in findings)
    f = next(f for f in findings if f.tag == "stdlib")
    assert "min" in f.replacement.lower()


def test_ponytail_shrink_array_syntax() -> None:
    diff_hunk = """@@ -20,5 +20,9 @@
+  do i = 1, n
+    arr(i) = 0.0
+  end do
"""
    findings = evaluate_ponytail_rules(
        "src/init.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert any(f.tag == "shrink" for f in findings)
    f = next(f for f in findings if f.tag == "shrink")
    assert "arr(:) = 0.0" in f.replacement
    assert f.patch is not None


def test_ponytail_nuopc_exemption() -> None:
    # Standard NUOPC dummy arguments like rc, clock, cdata must NOT trigger 'delete'
    diff_hunk = """@@ -1,5 +1,8 @@
+subroutine SetServices(gcomp, rc)
+  type(ESMF_GridComp) :: gcomp
+  integer, intent(out) :: rc
+  rc = ESMF_SUCCESS
+end subroutine
"""
    findings = evaluate_ponytail_rules(
        "src/cap.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert not any(f.tag == "delete" and "rc" in f.what_to_cut for f in findings)


def test_ponytail_openmp_simd_exemption() -> None:
    # Explicit loop with !$omp simd must NOT trigger 'shrink'
    diff_hunk = """@@ -1,5 +1,8 @@
+  !$omp simd
+  do i = 1, n
+    arr(i) = 0.0
+  end do
"""
    findings = evaluate_ponytail_rules(
        "src/compute.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert not any(f.tag == "shrink" for f in findings)
