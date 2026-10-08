"""File language detection and comment classification engine."""

import re
from pathlib import Path

from ufs_chem_pr_review_mcp.models.common import (
    ReviewCategory,
    SupportedLanguage,
)

FORTRAN_KEYWORDS = re.compile(
    r"\b(module|subroutine|function|use\s+\w+|implicit\s+none|end\s+subroutine|end\s+module)\b",
    re.IGNORECASE,
)
CPP_KEYWORDS = re.compile(
    r"(#include\s*<|std::|namespace\s+\w+|class\s+\w+|template\s*<)",
    re.IGNORECASE,
)

# Category keywords mapping
CATEGORY_RULES: list[tuple[ReviewCategory, list[str]]] = [
    (
        ReviewCategory.CHEMISTRY_PHYSICS,
        [
            "unit",
            "ppm",
            "ppb",
            "kg/kg",
            "molar",
            "molecular weight",
            "mw",
            "emission",
            "aerosol",
            "photolysis",
            "stoichiometry",
            "half-life",
            "reaction rate",
            "mixing ratio",
        ],
    ),
    (
        ReviewCategory.ESMF_NUOPC,
        [
            "nuopc",
            "esmf",
            "cap",
            "advertise",
            "realize",
            "importstate",
            "exportstate",
            "field dictionary",
            "coupling",
            "clock",
            "alarm",
            "esmf_logfounderror",
            "esmf_stateget",
        ],
    ),
    (
        ReviewCategory.CONCURRENCY_HPC,
        [
            "mpi_",
            "openmp",
            "omp",
            "thread",
            "deadlock",
            "barrier",
            "race condition",
            "kokkos",
            "offload",
            "cuda",
            "gpu",
            "bandwidth",
        ],
    ),
    (
        ReviewCategory.OVERENGINEERING,
        [
            "yagni",
            "over-engineer",
            "overengineered",
            "unused",
            "dead code",
            "unnecessary abstraction",
            "wrapper",
            "simplify",
            "boilerplate",
            "ponytail",
            "delete",
        ],
    ),
    (
        ReviewCategory.CORRECTNESS,
        [
            "bug",
            "crash",
            "segfault",
            "out of bounds",
            "uninitialized",
            "leak",
            "memory leak",
            "null",
            "nullptr",
            "nan",
            "infinity",
            "off-by-one",
            "divide by zero",
        ],
    ),
    (
        ReviewCategory.BUILD_PACKAGING,
        [
            "cmake",
            "spack",
            "compiler",
            "docker",
            "container",
            "target_link_libraries",
            "find_package",
            "build error",
            "dockerfile",
        ],
    ),
]


def detect_language(file_path: str, content: str | None = None) -> SupportedLanguage:
    """Detect language from file path extension, with content inspection for ambiguous headers."""
    path = Path(file_path)
    name = path.name.lower()
    suffix = path.suffix.lower()

    if name in ("cmakelists.txt",) or suffix == ".cmake":
        return SupportedLanguage.CMAKE
    if name in ("dockerfile", "containerfile") or suffix in (".dockerfile",):
        return SupportedLanguage.DOCKERFILE

    if suffix in (".f90", ".f95", ".f03", ".f08", ".f"):
        return SupportedLanguage.FORTRAN
    if suffix in (".cpp", ".cxx", ".cc", ".hpp", ".hxx"):
        return SupportedLanguage.CPP
    if suffix == ".c":
        return SupportedLanguage.C
    if suffix == ".py":
        return SupportedLanguage.PYTHON
    if suffix in (".sh", ".bash", ".zsh"):
        return SupportedLanguage.SHELL
    if suffix in (".yaml", ".yml"):
        return SupportedLanguage.YAML
    if suffix in (".md", ".markdown"):
        return SupportedLanguage.MARKDOWN

    # Ambiguous headers: .h and .inc
    if suffix in (".h", ".inc"):
        if content:
            if FORTRAN_KEYWORDS.search(content):
                return SupportedLanguage.FORTRAN
            if CPP_KEYWORDS.search(content):
                return SupportedLanguage.CPP
        if suffix == ".inc":
            return SupportedLanguage.FORTRAN
        return SupportedLanguage.C

    return SupportedLanguage.UNKNOWN


def classify_comment(
    body: str, has_diff_followup: bool = False
) -> tuple[ReviewCategory, int]:
    """Classify review comment into ReviewCategory and criticality rating (1 to 5)."""
    lower = body.lower()

    # Determine category
    assigned_category = ReviewCategory.STYLE_DOCS
    for category, keywords in CATEGORY_RULES:
        if any(kw in lower for kw in keywords):
            assigned_category = category
            break

    # Determine criticality
    # Blocker: crash, segfault, invalid physics/chemistry, data corruption
    if any(k in lower for k in ["crash", "segfault", "data corruption", "fatal"]):
        criticality = 5
    elif any(
        k in lower
        for k in [
            "leak",
            "uninitialized",
            "off-by-one",
            "race condition",
            "ppm",
            "molecular weight",
        ]
    ):
        criticality = 4 if has_diff_followup else 4
    elif assigned_category in (
        ReviewCategory.OVERENGINEERING,
        ReviewCategory.ESMF_NUOPC,
        ReviewCategory.BUILD_PACKAGING,
    ):
        criticality = 3
    elif any(
        k in lower for k in ["typo", "whitespace", "format", "spelling", "formatting"]
    ):
        criticality = 1
    elif any(k in lower for k in ["doc", "style", "comment", "rename", "refactor"]):
        criticality = 2
    else:
        criticality = 2 if not has_diff_followup else 3

    return assigned_category, criticality
