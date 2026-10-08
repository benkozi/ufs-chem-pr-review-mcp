"""Common enums and taxonomy for review categorization and outputs."""

from enum import Enum


class SupportedLanguage(str, Enum):
    """Programming or configuration language detected in PR diffs."""

    FORTRAN = "fortran"
    CPP = "cpp"
    C = "c"
    PYTHON = "python"
    SHELL = "shell"
    CMAKE = "cmake"
    DOCKERFILE = "dockerfile"
    YAML = "yaml"
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"


class ReviewCategory(str, Enum):
    """Classification taxonomy for review comments and rule findings."""

    OVERENGINEERING = "overengineering"
    CORRECTNESS = "correctness"
    CHEMISTRY_PHYSICS = "chemistry_physics"
    ESMF_NUOPC = "esmf_nuopc"
    CONCURRENCY_HPC = "concurrency_hpc"
    BUILD_PACKAGING = "build_packaging"
    CI_TESTING = "ci_testing"
    STYLE_DOCS = "style_docs"


class DiffFollowUpStatus(str, Enum):
    """Resolution status of code changes following a review comment."""

    CODE_MODIFIED = "code_modified"
    DISCUSSION_ONLY = "discussion_only"
    NO_RESPONSE = "no_response"
    REJECTED_EXPLAINED = "rejected_explained"


class OutputFormat(str, Enum):
    """Desired output serialization format for review evaluations."""

    GITHUB_JSON = "github_json"
    MARKDOWN = "markdown"
    PATCH = "patch"
    BOTH = "both"
    ALL = "all"


class ReviewMode(str, Enum):
    """Granularity mode of review output."""

    SUMMARY_AND_INLINE = "summary_and_inline"
    SUMMARY_ONLY = "summary_only"
    INLINE_ONLY = "inline_only"


class ReviewEvent(str, Enum):
    """GitHub Review action event type."""

    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    APPROVE = "APPROVE"
