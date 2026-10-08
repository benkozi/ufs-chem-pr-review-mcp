"""Ponytail over-engineering audit engine."""

import re

from ufs_chem_pr_review_mcp.models.common import SupportedLanguage
from ufs_chem_pr_review_mcp.models.mcp_tools import PonytailFinding
from ufs_chem_pr_review_mcp.models.patch import CodePatch

# Regex patterns for diff additions
COMMENTED_CODE_RE = re.compile(
    r"^\+\s*(!|#|//)\s*(call\s+|def\s+|x\s*=|y\s*=|if\s+|do\s+|for\s+)", re.IGNORECASE
)
CUSTOM_MIN_RE = re.compile(
    r"^\+\s*(def\s+custom_min|function\s+custom_min)", re.IGNORECASE
)
ARRAY_LOOP_START_RE = re.compile(
    r"^\+\s*do\s+([a-zA-Z0-9_]+)\s*=\s*1\s*,\s*([a-zA-Z0-9_]+)", re.IGNORECASE
)
ARRAY_ASSIGN_RE = re.compile(
    r"^\+\s*([a-zA-Z0-9_]+)\(([a-zA-Z0-9_]+)\)\s*=\s*(0\.0|0|1\.0|1)\b", re.IGNORECASE
)
OPENMP_SIMD_RE = re.compile(r"!\$omp\s+simd", re.IGNORECASE)


def evaluate_ponytail_rules(
    file_path: str,
    diff_hunk: str,
    language: SupportedLanguage,
) -> list[PonytailFinding]:
    """Audit diff additions for over-engineering, dead code, and collapsible boilerplate."""
    findings: list[PonytailFinding] = []
    lines = diff_hunk.splitlines()

    # Track line numbers
    current_line = 1
    has_omp_simd = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("@@"):
            # Parse diff hunk start line if available
            m = re.search(r"\+(\d+)", line)
            if m:
                current_line = int(m.group(1))
            i += 1
            continue

        if OPENMP_SIMD_RE.search(line):
            has_omp_simd = True

        if line.startswith("+"):
            content = line[1:]

            # 1. Check for commented-out dead code
            if COMMENTED_CODE_RE.match(line):
                orig_code = content + "\n"
                patch = CodePatch(
                    file_path=file_path,
                    start_line=current_line,
                    end_line=current_line,
                    original_code=orig_code,
                    replacement_code="",
                    unified_hunk=f"@@ -{current_line},1 +{current_line},0 @@\n-{content}\n",
                )
                findings.append(
                    PonytailFinding(
                        file_path=file_path,
                        line_number=current_line,
                        tag="delete",
                        what_to_cut="Commented-out dead code block",
                        replacement="Delete commented code",
                        lines_saved_estimate=1,
                        original_code=orig_code,
                        replacement_code="",
                        patch=patch,
                    )
                )

            # 2. Check for standard library reimplementation
            elif CUSTOM_MIN_RE.match(line):
                orig_code = content + "\n"
                findings.append(
                    PonytailFinding(
                        file_path=file_path,
                        line_number=current_line,
                        tag="stdlib",
                        what_to_cut="Reinventing custom min/max routine",
                        replacement="Use standard library min() / max()",
                        lines_saved_estimate=4,
                        original_code=orig_code,
                        replacement_code="min(a, b)",
                        patch=None,
                    )
                )

            # 3. Check for collapsible array initialization loop in Fortran
            m_loop = ARRAY_LOOP_START_RE.match(line)
            if m_loop and language == SupportedLanguage.FORTRAN and not has_omp_simd:
                loop_var = m_loop.group(1)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    m_assign = ARRAY_ASSIGN_RE.match(next_line)
                    if m_assign and m_assign.group(2) == loop_var:
                        arr_name = m_assign.group(1)
                        val = m_assign.group(3)
                        replacement = f"{arr_name}(:) = {val}"
                        orig = (
                            content
                            + "\n"
                            + next_line[1:]
                            + "\n"
                            + (lines[i + 2][1:] if i + 2 < len(lines) else "")
                            + "\n"
                        )
                        patch = CodePatch(
                            file_path=file_path,
                            start_line=current_line,
                            end_line=current_line + 2,
                            original_code=orig,
                            replacement_code=f"  {replacement}\n",
                            unified_hunk=f"@@ -{current_line},3 +{current_line},1 @@\n-{content}\n-{next_line[1:]}\n-  end do\n+  {replacement}\n",
                        )
                        findings.append(
                            PonytailFinding(
                                file_path=file_path,
                                line_number=current_line,
                                tag="shrink",
                                what_to_cut=f"Verbose scalar loop setting {arr_name}",
                                replacement=f"Use Fortran array syntax {replacement}",
                                lines_saved_estimate=2,
                                original_code=orig,
                                replacement_code=f"  {replacement}\n",
                                patch=patch,
                            )
                        )

            current_line += 1
        elif not line.startswith("-"):
            current_line += 1

        i += 1

    return findings
