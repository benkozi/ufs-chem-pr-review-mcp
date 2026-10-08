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


def evaluate_ufs_chem_rules(
    file_path: str,
    diff_hunk: str,
    language: SupportedLanguage,
) -> list[DomainFinding]:
    """Evaluate UFS atmospheric chemistry domain rules on diff additions."""
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

            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

    return findings
