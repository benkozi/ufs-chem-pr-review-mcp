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


def evaluate_ufs_chem_rules(
    file_path: str,
    diff_hunk: str,
    language: SupportedLanguage,
) -> list[DomainFinding]:
    """Evaluate UFS atmospheric chemistry and OMD/EE2 domain rules on diff additions."""
    findings: list[DomainFinding] = []
    lines = diff_hunk.splitlines()

    current_line = 1

    for line in lines:
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            if m:
                current_line = int(m.group(1))
            continue

        if line.startswith("+"):
            content = line[1:]

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

            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

    return findings
