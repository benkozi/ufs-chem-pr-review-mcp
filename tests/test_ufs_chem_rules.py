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


def test_omd_legacy_precision_types() -> None:
    diff_hunk = """@@ -1,5 +1,7 @@
+  real*8 :: conc_o3
+  real*4 :: temp_field
+  double precision :: pressure
"""
    findings = evaluate_ufs_chem_rules(
        "chem/species.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    legacy = [f for f in findings if f.rule_name == "legacy_precision_type"]
    assert len(legacy) == 3
    assert legacy[0].replacement_code == "real(wp)"
    assert legacy[0].patch is not None
    assert "real(wp)" in legacy[0].patch.replacement_code
    assert legacy[1].replacement_code == "real(sp)"
    assert legacy[2].replacement_code == "real(wp)"


def test_omd_openmp_default_none() -> None:
    diff_hunk = """@@ -20,6 +20,10 @@
+  !$omp parallel do
+  do i = 1, n
+  end do
+  !$omp parallel do default(none) shared(n)
+  !$omp parallel do &
+  !$omp& default(none)
"""
    findings = evaluate_ufs_chem_rules(
        "chem/advection.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    omp = [f for f in findings if f.rule_name == "openmp_missing_default_none"]
    assert len(omp) == 1
    assert omp[0].line_number == 20
    assert omp[0].category == ReviewCategory.CONCURRENCY_HPC
    assert omp[0].replacement_code is not None
    assert "default(none)" in omp[0].replacement_code


def test_omd_fortran_compute_kernel_direct_io() -> None:
    diff_kernel = """@@ -15,3 +15,5 @@
+  print *, "step converged"
+  write(6, *) "iteration done"
"""
    findings_kernel = evaluate_ufs_chem_rules(
        "chem/solvers/rosenbrock.F90", diff_kernel, SupportedLanguage.FORTRAN
    )
    io_findings = [
        f for f in findings_kernel if f.rule_name == "compute_kernel_direct_io"
    ]
    assert len(io_findings) == 2

    # In app/driver/test layer, direct I/O is permissible
    findings_app = evaluate_ufs_chem_rules(
        "app/driver_main.F90", diff_kernel, SupportedLanguage.FORTRAN
    )
    assert not any(f.rule_name == "compute_kernel_direct_io" for f in findings_app)


def test_omd_cpp_raw_owning_pointer() -> None:
    diff_hunk = """@@ -10,3 +10,5 @@
+  auto* solver = new RosenbrockSolver();
+  delete solver;
"""
    findings = evaluate_ufs_chem_rules(
        "chem/cpp/solver.cpp", diff_hunk, SupportedLanguage.CPP
    )
    raw_ptrs = [f for f in findings if f.rule_name == "cpp_raw_owning_pointer"]
    assert len(raw_ptrs) == 2
    assert "Forge Protocol" in raw_ptrs[0].explanation


def test_omd_cpp_compute_kernel_direct_io() -> None:
    diff_kernel = """@@ -10,3 +10,4 @@
+  std::cout << "Iteration " << i << std::endl;
"""
    findings_kernel = evaluate_ufs_chem_rules(
        "src/core/solver.cpp", diff_kernel, SupportedLanguage.CPP
    )
    assert any(f.rule_name == "cpp_compute_kernel_direct_io" for f in findings_kernel)

    findings_app = evaluate_ufs_chem_rules(
        "app/cli_runner.cpp", diff_kernel, SupportedLanguage.CPP
    )
    assert not any(f.rule_name == "cpp_compute_kernel_direct_io" for f in findings_app)


def test_ee2_shell_background_process() -> None:
    diff_hunk = """@@ -5,3 +5,5 @@
+  # This is a comment about &
+  srun -n 36 ./ufs_model.x &
"""
    findings = evaluate_ufs_chem_rules(
        "scripts/run_forecast.sh", diff_hunk, SupportedLanguage.SHELL
    )
    bg_findings = [f for f in findings if f.rule_name == "ee2_shell_background_process"]
    assert len(bg_findings) == 1
    assert bg_findings[0].category == ReviewCategory.CONCURRENCY_HPC
    assert "NCO EE2" in bg_findings[0].explanation


def test_ee2_hardcoded_path() -> None:
    diff_hunk = """@@ -1,3 +1,5 @@
+  DATA_PATH="/scratch/users/model_out"
+  INPUT_PATH="/gpfs/data/meteo/inputs"
"""
    findings = evaluate_ufs_chem_rules(
        "scripts/jjob.sh", diff_hunk, SupportedLanguage.SHELL
    )
    paths = [f for f in findings if f.rule_name == "ee2_hardcoded_path"]
    assert len(paths) == 2
    assert paths[0].category == ReviewCategory.BUILD_PACKAGING
    assert "$DATA" in paths[0].explanation


def test_omd_python_lazy_breaker() -> None:
    diff_hunk = """@@ -10,3 +10,5 @@
+  processed = ds["o3"].compute()
+  loaded = da.load()
"""
    findings = evaluate_ufs_chem_rules(
        "pychem/postprocess.py", diff_hunk, SupportedLanguage.PYTHON
    )
    breakers = [f for f in findings if f.rule_name == "python_dask_lazy_breaker"]
    assert len(breakers) == 2
    assert breakers[0].category == ReviewCategory.CONCURRENCY_HPC
    assert "Aero Protocol" in breakers[0].explanation
