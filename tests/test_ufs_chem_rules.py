"""Unit tests for UFS-Chem atmospheric chemistry domain rules."""

from ufs_chem_pr_review_mcp.models.common import (
    ReviewCategory,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.rules.ufs_chem import evaluate_ufs_chem_rules


def test_ufs_chem_single_precision_literal() -> None:
    diff_hunk = """@@ -10,3 +10,4 @@
+  real(rk) :: rate
+  rate = 1.0 * temp
"""
    findings = evaluate_ufs_chem_rules(
        "chem/rates.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert any(f.rule_name == "single_precision_literal" for f in findings)
    f = next(f for f in findings if f.rule_name == "single_precision_literal")
    assert f.category == ReviewCategory.CHEMISTRY_PHYSICS
    assert "1.0_rk" in f.explanation
    assert f.patch is not None
    assert f.replacement_code == "1.0_rk"


def test_ufs_chem_missing_allocate_stat() -> None:
    diff_hunk = """@@ -50,3 +50,4 @@
+  allocate(tracer_concs(imax, jmax, kmax))
"""
    findings = evaluate_ufs_chem_rules(
        "chem/grid.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert any(f.rule_name == "missing_allocate_stat" for f in findings)
    f = next(f for f in findings if f.rule_name == "missing_allocate_stat")
    assert f.category == ReviewCategory.CORRECTNESS
    assert "stat=" in f.explanation
    assert f.patch is not None
    assert f.replacement_code is not None
    assert "stat=rc" in f.replacement_code or "stat=" in f.replacement_code


def test_ufs_chem_missing_esmf_return_check() -> None:
    diff_hunk = """@@ -30,4 +30,5 @@
+  call ESMF_StateGet(exportState, "O3", field, rc=rc)
+  call process_o3(field)
"""
    findings = evaluate_ufs_chem_rules(
        "cap/chem_cap.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert any(f.rule_name == "missing_esmf_return_code_check" for f in findings)
    f = next(f for f in findings if f.rule_name == "missing_esmf_return_code_check")
    assert f.category == ReviewCategory.ESMF_NUOPC
    assert "ESMF_LogFoundError" in f.explanation


def test_ufs_chem_unit_conversion_molecular_weight() -> None:
    diff_hunk = """@@ -100,3 +100,4 @@
+  q_kgkg = conc_ppm * 1.0e-6
"""
    findings = evaluate_ufs_chem_rules(
        "chem/units.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    assert any(f.rule_name == "chemistry_unit_molecular_weight" for f in findings)
    f = next(f for f in findings if f.rule_name == "chemistry_unit_molecular_weight")
    assert f.category == ReviewCategory.CHEMISTRY_PHYSICS
    assert "molecular weight" in f.explanation.lower()
