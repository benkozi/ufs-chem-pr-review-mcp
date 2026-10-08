"""Unit tests for comment classification and language detection."""

from ufs_chem_pr_review_mcp.ingest.classifier import (
    classify_comment,
    detect_language,
)
from ufs_chem_pr_review_mcp.models.common import (
    ReviewCategory,
    SupportedLanguage,
)


def test_detect_language_by_extension() -> None:
    assert detect_language("src/chem.F90") == SupportedLanguage.FORTRAN
    assert detect_language("src/driver.f90") == SupportedLanguage.FORTRAN
    assert detect_language("chem/core.cpp") == SupportedLanguage.CPP
    assert detect_language("include/header.hpp") == SupportedLanguage.CPP
    assert detect_language("scripts/run.py") == SupportedLanguage.PYTHON
    assert detect_language("scripts/run.sh") == SupportedLanguage.SHELL
    assert detect_language("CMakeLists.txt") == SupportedLanguage.CMAKE
    assert detect_language("cmake/FindNetCDF.cmake") == SupportedLanguage.CMAKE
    assert detect_language("docker/Dockerfile") == SupportedLanguage.DOCKERFILE
    assert detect_language("config/model.yaml") == SupportedLanguage.YAML
    assert detect_language("docs/README.md") == SupportedLanguage.MARKDOWN
    assert detect_language("data/input.dat") == SupportedLanguage.UNKNOWN


def test_detect_language_header_disambiguation() -> None:
    # .h file containing Fortran keywords
    fortran_h = "subroutine chem_init()\n  implicit none\nend subroutine"
    assert (
        detect_language("include/chem_defs.h", content=fortran_h)
        == SupportedLanguage.FORTRAN
    )

    # .h file containing C/C++ keywords
    cpp_h = "#include <iostream>\nnamespace chem { void init(); }"
    assert (
        detect_language("include/chem_defs.h", content=cpp_h) == SupportedLanguage.CPP
    )

    # .h file with no content defaults to C
    assert detect_language("include/chem_defs.h") == SupportedLanguage.C

    # .inc file containing Fortran keywords
    fortran_inc = "use chem_const_mod, only: pi"
    assert (
        detect_language("include/params.inc", content=fortran_inc)
        == SupportedLanguage.FORTRAN
    )


def test_classify_comment_chemistry_physics() -> None:
    body = "Missing molecular weight normalization in ppm to kg/kg unit conversion"
    cat, crit = classify_comment(body, has_diff_followup=True)
    assert cat == ReviewCategory.CHEMISTRY_PHYSICS
    assert crit >= 4


def test_classify_comment_esmf_nuopc() -> None:
    body = "Check ESMF_LogFoundError return code after ESMF_StateGet call"
    cat, crit = classify_comment(body, has_diff_followup=False)
    assert cat == ReviewCategory.ESMF_NUOPC
    assert crit >= 3


def test_classify_comment_concurrency_hpc() -> None:
    body = "Possible race condition in openmp parallel do loop over grid cells"
    cat, crit = classify_comment(body, has_diff_followup=True)
    assert cat == ReviewCategory.CONCURRENCY_HPC
    assert crit >= 4


def test_classify_comment_overengineering() -> None:
    body = "This wrapper is unnecessary yagni over-engineered boilerplate, delete it"
    cat, crit = classify_comment(body, has_diff_followup=False)
    assert cat == ReviewCategory.OVERENGINEERING
    assert crit == 3


def test_classify_comment_correctness_and_criticality() -> None:
    body = "Severe memory leak caused by unallocated buffer in error path"
    cat, crit = classify_comment(body, has_diff_followup=True)
    assert cat == ReviewCategory.CORRECTNESS
    assert crit == 4

    crash_body = "Fatal segfault crash when array index is out of bounds"
    cat, crit = classify_comment(crash_body, has_diff_followup=True)
    assert cat == ReviewCategory.CORRECTNESS
    assert crit == 5


def test_detect_language_c_and_inc_fallback() -> None:
    assert detect_language("src/legacy.c") == SupportedLanguage.C
    assert detect_language("include/defaults.inc") == SupportedLanguage.FORTRAN


def test_classify_comment_style_and_nits() -> None:
    body = "Minor typo in the comment and whitespace formatting"
    cat, crit = classify_comment(body, has_diff_followup=False)
    assert cat == ReviewCategory.STYLE_DOCS
    assert crit == 1

    doc_body = "Please update doc string and rename parameter"
    cat, crit = classify_comment(doc_body, has_diff_followup=False)
    assert cat == ReviewCategory.STYLE_DOCS
    assert crit == 2

    generic_body = "Looks interesting, let us test this."
    cat, crit = classify_comment(generic_body, has_diff_followup=False)
    assert crit == 2
    cat, crit = classify_comment(generic_body, has_diff_followup=True)
    assert crit == 3
