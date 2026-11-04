"""Domain-specific correctness rules for UFS atmospheric chemistry code."""

import re

from ufs_chem_pr_review_mcp.models.common import (
    ReviewCategory,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.models.mcp_tools import DomainFinding
from ufs_chem_pr_review_mcp.models.patch import CodePatch

SINGLE_PREC_RE = re.compile(r"^\+.*?\b([0-9]+\.[0-9]+)\b(?![a-zA-Z0-9_dD])")
ALLOCATE_NO_STAT_RE = re.compile(r"^\+\s*allocate\s*\((.*?)\)", re.IGNORECASE)
ESMF_STATE_GET_RE = re.compile(r"^\+\s*call\s+ESMF_StateGet\s*\(", re.IGNORECASE)
UNIT_CONV_RE = re.compile(r"^\+.*?(?:ppm|ppb).*?[*\/].*?1\.0[eE]-0?6", re.IGNORECASE)

# NOAA OMD & NCO EE2 Rules
LEGACY_PREC_RE = re.compile(r"^\+.*?\b(real\*[48]|double\s+precision)\b", re.IGNORECASE)
OMP_PARALLEL_RE = re.compile(
    r"^\+\s*!\$omp\s+(?:parallel(?:\s+do)?|do(?:\s+concurrent)?)\b", re.IGNORECASE
)
FORTRAN_IO_RE = re.compile(
    r"^\+\s*(?:print\s*\*|write\s*\(\s*(?:\*|6)\s*,)", re.IGNORECASE
)
CPP_RAW_PTR_RE = re.compile(
    r"^\+.*?\b(new\s+[a-zA-Z0-9_]+|delete(?:\s*\[\s*\])?\s+[a-zA-Z0-9_]+)\b"
)
CPP_IO_RE = re.compile(r"^\+.*?\bstd::cout\b")
SHELL_BG_RE = re.compile(r"^\+[^#\n]*[^\w\-&]\&\s*$")
HARDCODED_PATH_RE = re.compile(
    r"^\+.*?(/(?:scratch|gpfs|work|ptmp)/[a-zA-Z0-9_\-\./]+)", re.IGNORECASE
)
PY_LAZY_BREAKER_RE = re.compile(r"^\+.*?\.(?:compute|load)\s*\(\s*\)")

# New OMD-Skills Rules (GitHub Actions, Fortran Floats, C Unsafe, EE2 Prefixes)
GHA_INJECTION_SINK_RE = re.compile(
    r"\$\{\{\s*github\.(?:event\.(?:issue|pull_request|comment|review|head_commit|commits)\b|head_ref\b)",
    re.IGNORECASE,
)
GHA_USES_RE = re.compile(r"^\+\s*-\s*uses:\s*([^@\s]+)@([^\s#]+)")
FORTRAN_EXACT_FLOAT_RE = re.compile(
    r"^\+\s*if\s*\([^)]*?(?:==|\.eq\.|/=|\.ne\.)\s*0\.0(?:_[a-zA-Z0-9_]+|[dDeE][+-]?\d+)?\b|^\+\s*if\s*\([^)]*?0\.0(?:_[a-zA-Z0-9_]+|[dDeE][+-]?\d+)?\s*(?:==|\.eq\.|/=|\.ne\.)",
    re.IGNORECASE,
)
C_UNSAFE_BUFFER_RE = re.compile(r"^\+.*?\b(strcpy|strcat|sprintf|vsprintf|gets)\s*\(")
EE2_MISSING_FATAL_RE = re.compile(
    r"^\+.*?\b(?:echo|printf)\s+[\"']\s*(?:ERROR|Error|FATAL|Fatal)\b(?!\s*ERROR:)",
    re.IGNORECASE,
)


def evaluate_ufs_chem_rules(
    file_path: str,
    diff_hunk: str,
    language: SupportedLanguage,
) -> list[DomainFinding]:
    """Evaluate UFS atmospheric chemistry and OMD/EE2 domain rules on diff additions."""
    findings: list[DomainFinding] = []
    lines = diff_hunk.splitlines()

    is_workflow_file = any(
        part in file_path.replace("\\", "/")
        for part in [".github/workflows", ".github/actions"]
    )
    in_run_block = False

    current_line = 1

    for line in lines:
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            if m:
                current_line = int(m.group(1))
            continue

        if line.startswith("+"):
            content = line[1:]

            if is_workflow_file:
                trimmed = content.strip()
                if trimmed.startswith("run:"):
                    if trimmed in ("run:", "run: |", "run: >"):
                        in_run_block = True
                    else:
                        in_run_block = False
                elif trimmed.startswith(
                    ("- ", "env:", "uses:", "with:", "name:", "id:", "if:")
                ):
                    in_run_block = False

            # 1. Fortran single-precision literal
            if language == SupportedLanguage.FORTRAN:
                m_lit = SINGLE_PREC_RE.search(line)
                if m_lit and not any(
                    x in line for x in ["_rk", "_r8", "d0", "D0", "stat="]
                ):
                    num = m_lit.group(1)
                    repl = f"{num}_rk"
                    patch = CodePatch(
                        file_path=file_path,
                        start_line=current_line,
                        end_line=current_line,
                        original_code=content + "\n",
                        replacement_code=content.replace(num, repl, 1) + "\n",
                        unified_hunk=f"@@ -{current_line},1 +{current_line},1 @@\n-{content}\n+{content.replace(num, repl, 1)}\n",
                    )
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="single_precision_literal",
                            category=ReviewCategory.CHEMISTRY_PHYSICS,
                            criticality=4,
                            explanation=f"Single-precision literal {num} in floating-point calculation. Use {repl} or double precision suffix.",
                            original_code=num,
                            replacement_code=repl,
                            patch=patch,
                        )
                    )

            # 2. Allocate without stat= checks
            if language == SupportedLanguage.FORTRAN and ALLOCATE_NO_STAT_RE.search(
                line
            ):
                if "stat=" not in line.lower():
                    replacement_line = content.rstrip()
                    if replacement_line.endswith(")"):
                        replacement_line = (
                            replacement_line[:-1] + ", stat=rc, errmsg=msg)"
                        )
                    patch = CodePatch(
                        file_path=file_path,
                        start_line=current_line,
                        end_line=current_line,
                        original_code=content + "\n",
                        replacement_code=replacement_line + "\n",
                        unified_hunk=f"@@ -{current_line},1 +{current_line},1 @@\n-{content}\n+{replacement_line}\n",
                    )
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="missing_allocate_stat",
                            category=ReviewCategory.CORRECTNESS,
                            criticality=4,
                            explanation="Fortran allocate statement lacks stat= and errmsg= status error checking.",
                            original_code=content.strip(),
                            replacement_code="stat=rc, errmsg=msg",
                            patch=patch,
                        )
                    )

            # 3. ESMF_StateGet without error check
            if language == SupportedLanguage.FORTRAN and ESMF_STATE_GET_RE.search(line):
                findings.append(
                    DomainFinding(
                        file_path=file_path,
                        line_number=current_line,
                        rule_name="missing_esmf_return_code_check",
                        category=ReviewCategory.ESMF_NUOPC,
                        criticality=4,
                        explanation="Call to ESMF_StateGet requires checking return code via if (ESMF_LogFoundError(rc, msg=...)) return.",
                        original_code=content.strip(),
                        replacement_code=None,
                        patch=None,
                    )
                )

            # 4. Chemistry unit conversion without molecular weight
            if UNIT_CONV_RE.search(line):
                findings.append(
                    DomainFinding(
                        file_path=file_path,
                        line_number=current_line,
                        rule_name="chemistry_unit_molecular_weight",
                        category=ReviewCategory.CHEMISTRY_PHYSICS,
                        criticality=5,
                        explanation="Conversion between molar mixing ratio (ppm) and mass mixing ratio (kg/kg) requires molecular weight ratio (M_spec / M_air).",
                        original_code=content.strip(),
                        replacement_code=None,
                        patch=None,
                    )
                )

            # 5. Fortran legacy precision types (Flux Protocol)
            if language == SupportedLanguage.FORTRAN:
                m_leg = LEGACY_PREC_RE.search(line)
                if m_leg:
                    matched = m_leg.group(1)
                    repl = "real(sp)" if "4" in matched else "real(wp)"
                    patch = CodePatch(
                        file_path=file_path,
                        start_line=current_line,
                        end_line=current_line,
                        original_code=content + "\n",
                        replacement_code=content.replace(matched, repl, 1) + "\n",
                        unified_hunk=f"@@ -{current_line},1 +{current_line},1 @@\n-{content}\n+{content.replace(matched, repl, 1)}\n",
                    )
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="legacy_precision_type",
                            category=ReviewCategory.CHEMISTRY_PHYSICS,
                            criticality=4,
                            explanation=f"Legacy precision type '{matched}' detected. OMD Fortran standards (Flux Protocol) mandate portable kind types from iso_fortran_env (e.g. real(wp) or real64).",
                            original_code=matched,
                            replacement_code=repl,
                            patch=patch,
                        )
                    )

            # 6. Fortran OpenMP missing default(none)
            if language == SupportedLanguage.FORTRAN:
                m_omp = OMP_PARALLEL_RE.search(line)
                if (
                    m_omp
                    and "default(" not in line.lower()
                    and not line.rstrip().endswith("&")
                ):
                    repl_line = content.rstrip() + " default(none)"
                    patch = CodePatch(
                        file_path=file_path,
                        start_line=current_line,
                        end_line=current_line,
                        original_code=content + "\n",
                        replacement_code=repl_line + "\n",
                        unified_hunk=f"@@ -{current_line},1 +{current_line},1 @@\n-{content}\n+{repl_line}\n",
                    )
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="openmp_missing_default_none",
                            category=ReviewCategory.CONCURRENCY_HPC,
                            criticality=4,
                            explanation="OpenMP parallel loop lacks 'default(none)'. OMD Fortran standards mandate explicit compile-time variable scoping to prevent data races.",
                            original_code=content.strip(),
                            replacement_code=repl_line.strip(),
                            patch=patch,
                        )
                    )

            # 7. Fortran compute kernel direct I/O
            if language == SupportedLanguage.FORTRAN and not any(
                k in file_path.lower() for k in ["app/", "test/", "tests/", "driver"]
            ):
                if FORTRAN_IO_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="compute_kernel_direct_io",
                            category=ReviewCategory.CORRECTNESS,
                            criticality=3,
                            explanation="Direct stdout write/print in core compute kernel. OMD standards require compute kernels to be compute-only; operational I/O belongs in driver/app layers.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 8. C++ raw owning pointers (Forge Protocol)
            if language in (SupportedLanguage.CPP, SupportedLanguage.C):
                m_raw = CPP_RAW_PTR_RE.search(line)
                if m_raw:
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="cpp_raw_owning_pointer",
                            category=ReviewCategory.CORRECTNESS,
                            criticality=4,
                            explanation="Raw pointer manual memory management (new/delete). OMD C++ guidelines (Forge Protocol) mandate strict RAII using smart pointers (std::unique_ptr / std::shared_ptr).",
                            original_code=m_raw.group(1),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 9. C++ compute kernel direct stdout
            if language == SupportedLanguage.CPP and not any(
                k in file_path.lower() for k in ["app/", "test/", "tests/", "driver"]
            ):
                if CPP_IO_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="cpp_compute_kernel_direct_io",
                            category=ReviewCategory.STYLE_DOCS,
                            criticality=3,
                            explanation="Direct std::cout in core compute kernel/header. OMD guidelines require compute-only kernels; operational logging belongs in driver/app layers.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 10. EE2 shell background process
            if language == SupportedLanguage.SHELL or file_path.endswith(
                (".sh", ".bash")
            ):
                if SHELL_BG_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="ee2_shell_background_process",
                            category=ReviewCategory.CONCURRENCY_HPC,
                            criticality=4,
                            explanation="Background process (&) detected. NCO EE2 standards forbid background processing because workload managers (PBS Pro/Slurm) lose tracking and control.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 11. EE2 hardcoded scratch/operational path
            m_path = HARDCODED_PATH_RE.search(line)
            if m_path:
                path_str = m_path.group(1)
                findings.append(
                    DomainFinding(
                        file_path=file_path,
                        line_number=current_line,
                        rule_name="ee2_hardcoded_path",
                        category=ReviewCategory.BUILD_PACKAGING,
                        criticality=4,
                        explanation=f"Hardcoded absolute operational path '{path_str}' detected. NCO EE2 standards strictly forbid hardcoded paths; use standard environment variables ($DATA, $COMROOT, $EXECmodel).",
                        original_code=path_str,
                        replacement_code=None,
                        patch=None,
                    )
                )

            # 12. Python lazy task graph breaker (Aero Protocol)
            if language == SupportedLanguage.PYTHON:
                if PY_LAZY_BREAKER_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="python_dask_lazy_breaker",
                            category=ReviewCategory.CONCURRENCY_HPC,
                            criticality=3,
                            explanation="Direct .compute()/.load() call inside data processing function breaks Dask laziness and risks node OOM. OMD Python standards (Aero Protocol) require preserving lazy execution.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 13. GitHub Actions untrusted script injection
            if is_workflow_file:
                if (in_run_block or "run:" in content) and "env:" not in content:
                    if GHA_INJECTION_SINK_RE.search(content):
                        findings.append(
                            DomainFinding(
                                file_path=file_path,
                                line_number=current_line,
                                rule_name="gha_untrusted_script_injection",
                                category=ReviewCategory.CORRECTNESS,
                                criticality=5,
                                explanation="Untrusted GitHub Actions context '${{ ... }}' interpolated directly inside script run block. Sinks such as issue/PR titles or branch names allow arbitrary code injection. Pass via intermediate env: variable instead.",
                                original_code=content.strip(),
                                replacement_code=None,
                                patch=None,
                            )
                        )

            # 14. GitHub Actions unpinned third-party action
            if is_workflow_file:
                m_uses = GHA_USES_RE.search(line)
                if m_uses:
                    action_name = m_uses.group(1).strip()
                    ref = m_uses.group(2).strip()
                    is_first_party = action_name.startswith(
                        ("actions/", "github/", "docker://", "./", "../")
                    )
                    is_sha = bool(re.match(r"^[0-9a-fA-F]{40}$", ref))
                    if not is_first_party and not is_sha:
                        findings.append(
                            DomainFinding(
                                file_path=file_path,
                                line_number=current_line,
                                rule_name="gha_unpinned_third_party_action",
                                category=ReviewCategory.BUILD_PACKAGING,
                                criticality=4,
                                explanation=f"Third-party action '{action_name}' is referenced by mutable tag/branch '@{ref}'. OMD GitHub Actions standards mandate pinning third-party actions to a full 40-character commit SHA with a version comment.",
                                original_code=content.strip(),
                                replacement_code=None,
                                patch=None,
                            )
                        )

            # 15. Fortran exact floating-point equality
            if language == SupportedLanguage.FORTRAN:
                if FORTRAN_EXACT_FLOAT_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="fortran_exact_float_equality",
                            category=ReviewCategory.CHEMISTRY_PHYSICS,
                            criticality=4,
                            explanation="Exact floating-point equality/inequality comparison (== 0.0 or /= 0.0) in numerical logic. Due to rounding errors, compiler optimizations, and reduction order differences across ranks, exact equality is non-portable. Compare using an explicit absolute/relative tolerance (e.g. abs(val) <= tol).",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 16. C / C++ unsafe string / buffer calls
            if language in (SupportedLanguage.C, SupportedLanguage.CPP):
                m_unsafe = C_UNSAFE_BUFFER_RE.search(line)
                if m_unsafe:
                    fn_name = m_unsafe.group(1)
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="c_unsafe_buffer_or_shell_call",
                            category=ReviewCategory.CORRECTNESS,
                            criticality=5,
                            explanation=f"Unsafe C string function '{fn_name}' detected. OMD standards prohibit unbounded buffer copies; use snprintf with size validation or C++ RAII string types.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            # 17. EE2 missing FATAL ERROR: prefix
            if language == SupportedLanguage.SHELL or file_path.endswith(
                (".sh", ".bash")
            ):
                if EE2_MISSING_FATAL_RE.search(line):
                    findings.append(
                        DomainFinding(
                            file_path=file_path,
                            line_number=current_line,
                            rule_name="ee2_missing_fatal_error_prefix",
                            category=ReviewCategory.STYLE_DOCS,
                            criticality=3,
                            explanation="Error message lacks mandatory NCO EE2 prefix. EE2 [portable] standards require fatal errors to begin with 'FATAL ERROR:' and non-fatal warnings with 'WARNING:'.",
                            original_code=content.strip(),
                            replacement_code=None,
                            patch=None,
                        )
                    )

            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

    return findings
