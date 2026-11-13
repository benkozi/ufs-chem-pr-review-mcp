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


def test_gha_untrusted_script_injection() -> None:
    # Trigger on direct interpolation in run:
    bad_diff = """@@ -15,3 +15,9 @@
+    - name: Print Title
+      run: echo "Title is ${{ github.event.pull_request.title }}"
+    - name: Checkout Head
+      run: git checkout ${{ github.head_ref }}
+    - name: Multiline Run
+      run: |
+        echo "Processing ${{ github.event.issue.body }}"
"""
    findings_bad = evaluate_ufs_chem_rules(
        ".github/workflows/ci.yml", bad_diff, SupportedLanguage.SHELL
    )
    injections = [
        f for f in findings_bad if f.rule_name == "gha_untrusted_script_injection"
    ]
    assert len(injections) == 3
    assert injections[0].criticality == 5
    assert injections[0].category == ReviewCategory.CORRECTNESS
    assert "intermediate env:" in injections[0].explanation.lower()

    # Should NOT trigger when ${{ }} is in env: block
    safe_diff = """@@ -20,4 +20,7 @@
+    - name: Safe Step
+      env:
+        PR_TITLE: ${{ github.event.pull_request.title }}
+      run: echo "$PR_TITLE"
"""
    findings_safe = evaluate_ufs_chem_rules(
        ".github/workflows/ci.yml", safe_diff, SupportedLanguage.SHELL
    )
    assert not any(
        f.rule_name == "gha_untrusted_script_injection" for f in findings_safe
    )


def test_gha_unpinned_third_party_action() -> None:
    diff_hunk = """@@ -10,4 +10,8 @@
+    - uses: actions/checkout@v4
+    - uses: softprops/action-gh-release@v1
+    - uses: codecov/codecov-action@v3
+    - uses: pre-commit/action@646c83fcd040023954eafda54b373a9cb768947a # v3.0.0
"""
    findings = evaluate_ufs_chem_rules(
        ".github/workflows/release.yml", diff_hunk, SupportedLanguage.SHELL
    )
    unpinned = [f for f in findings if f.rule_name == "gha_unpinned_third_party_action"]
    assert len(unpinned) == 2
    assert unpinned[0].criticality == 4
    assert unpinned[0].category == ReviewCategory.BUILD_PACKAGING
    assert "softprops/action-gh-release" in unpinned[0].explanation
    assert "codecov/codecov-action" in unpinned[1].explanation


def test_fortran_exact_float_equality() -> None:
    diff_hunk = """@@ -40,4 +40,7 @@
+  if (residual == 0.0_rk) exit
+  if (val .eq. 0.0) return
+  if (diff /= 0.0d0) then
+  if (counter == 0) continue
"""
    findings = evaluate_ufs_chem_rules(
        "chem/solver.F90", diff_hunk, SupportedLanguage.FORTRAN
    )
    exact_floats = [
        f for f in findings if f.rule_name == "fortran_exact_float_equality"
    ]
    assert len(exact_floats) == 3
    assert exact_floats[0].criticality == 4
    assert exact_floats[0].category == ReviewCategory.CHEMISTRY_PHYSICS
    assert "tolerance" in exact_floats[0].explanation.lower()


def test_c_unsafe_buffer_or_shell_call() -> None:
    diff_hunk = """@@ -25,4 +25,7 @@
+  strcpy(dest, src);
+  sprintf(buf, "%s", name);
+  gets(input);
+  snprintf(safe_buf, sizeof(safe_buf), "%s", name);
"""
    findings = evaluate_ufs_chem_rules("src/util.c", diff_hunk, SupportedLanguage.C)
    unsafe_calls = [
        f for f in findings if f.rule_name == "c_unsafe_buffer_or_shell_call"
    ]
    assert len(unsafe_calls) == 3
    assert unsafe_calls[0].criticality == 5
    assert unsafe_calls[0].category == ReviewCategory.CORRECTNESS
    assert "strcpy" in unsafe_calls[0].explanation


def test_ee2_missing_fatal_error_prefix() -> None:
    diff_hunk = """@@ -12,3 +12,6 @@
+  echo "ERROR: Missing GFS meteorological file"
+  printf 'Fatal: input data corrupted\n'
+  echo "FATAL ERROR: Missing grid geometry file"
"""
    findings = evaluate_ufs_chem_rules(
        "scripts/ex_driver.sh", diff_hunk, SupportedLanguage.SHELL
    )
    missing_prefix = [
        f for f in findings if f.rule_name == "ee2_missing_fatal_error_prefix"
    ]
    assert len(missing_prefix) == 2
    assert missing_prefix[0].criticality == 3
    assert missing_prefix[0].category == ReviewCategory.STYLE_DOCS
    assert "FATAL ERROR:" in missing_prefix[0].explanation
