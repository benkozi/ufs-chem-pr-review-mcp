"""Input and output schemas for MCP tools and resources."""

from pydantic import BaseModel, ConfigDict, Field

from ufs_chem_pr_review_mcp.models.common import (
    OutputFormat,
    ReviewCategory,
    ReviewMode,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.models.patch import CodePatch
from ufs_chem_pr_review_mcp.models.review import ReviewCommentRecord


class EvaluatePrInput(BaseModel):
    """Input payload for evaluate_pr MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str = Field(
        description="Target repository in owner/repo format, e.g. 'ufs-community/CATChem'"
    )
    pr_number: int = Field(
        ge=1, description="Pull request number on GitHub to evaluate"
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Desired output format: markdown, github_json, patch, both, or all",
    )
    review_mode: ReviewMode = Field(
        default=ReviewMode.SUMMARY_AND_INLINE,
        description="Review detail mode: summary_and_inline, summary_only, or inline_only",
    )
    include_ponytail_audit: bool = Field(
        default=True, description="Whether to include ponytail over-engineering checks"
    )
    max_context_comments: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Maximum number of historical matching comments to retrieve",
    )


class EvaluateDiffInput(BaseModel):
    """Input payload for evaluate_diff MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_text: str = Field(description="Unified git diff text to evaluate")
    target_repo: str = Field(
        default="ufs-community/CATChem",
        description="Repository context to match historical rules against",
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MARKDOWN,
        description="Desired output format: markdown, github_json, patch, both, or all",
    )
    review_mode: ReviewMode = Field(
        default=ReviewMode.SUMMARY_AND_INLINE,
        description="Review detail mode: summary_and_inline, summary_only, or inline_only",
    )
    include_ponytail_audit: bool = Field(
        default=True, description="Whether to include ponytail over-engineering checks"
    )
    max_context_comments: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Maximum number of historical matching comments to retrieve",
    )


class SearchReviewHistoryInput(BaseModel):
    """Input payload for search_review_history MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(
        description="Full-text search query across historical comments and code snippets"
    )
    repo: str | None = Field(
        default=None, description="Optional filter by repository name"
    )
    language: SupportedLanguage | None = Field(
        default=None, description="Optional filter by language"
    )
    category: ReviewCategory | None = Field(
        default=None, description="Optional filter by review category"
    )
    min_criticality: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Filter for comments with criticality >= min_criticality",
    )
    has_diff_followup_only: bool = Field(
        default=False,
        description="Filter for comments that successfully prompted code modifications",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")


class PonytailFinding(BaseModel):
    """Over-engineering finding identified by Ponytail heuristics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_path: str = Field(description="Path to the file evaluated")
    line_number: int = Field(description="Line number in the new code")
    tag: str = Field(description="Ponytail tag: delete, stdlib, native, yagni, shrink")
    what_to_cut: str = Field(description="Specific over-engineering element to cut")
    replacement: str = Field(
        description="Suggested lean replacement or standard library alternative"
    )
    lines_saved_estimate: int = Field(
        ge=0, description="Estimated lines of code removable"
    )
    original_code: str | None = Field(
        default=None,
        description="Exact lines of code identified for removal or simplification",
    )
    replacement_code: str | None = Field(
        default=None,
        description="Exact drop-in replacement code (empty string if deleted)",
    )
    patch: CodePatch | None = Field(
        default=None, description="Machine-applicable code patch hunk"
    )


class DomainFinding(BaseModel):
    """Domain-specific correctness finding for atmospheric chemistry code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_path: str = Field(description="Path to the file evaluated")
    line_number: int = Field(description="Line number in the new code")
    rule_name: str = Field(
        description="Domain rule name, e.g. chemistry_unit_mismatch, nuopc_state_leaking"
    )
    category: ReviewCategory = Field(description="Category of the domain finding")
    criticality: int = Field(ge=1, le=5, description="Criticality ranking (1 to 5)")
    explanation: str = Field(
        description="Explanation of the domain finding and recommendation"
    )
    original_code: str | None = Field(
        default=None,
        description="Exact problematic code snippet identified by domain rule",
    )
    replacement_code: str | None = Field(
        default=None, description="Exact corrected replacement snippet"
    )
    patch: CodePatch | None = Field(
        default=None, description="Machine-applicable code patch hunk"
    )


class ReviewContextResponse(BaseModel):
    """Structured context payload served by evaluate_pr and evaluate_diff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str = Field(description="Repository evaluated")
    pr_number: int | None = Field(
        default=None, description="PR number, if evaluated from GitHub"
    )
    review_mode: ReviewMode = Field(description="Review mode requested")
    touched_files: list[str] = Field(description="List of files modified in the PR")
    detected_languages: list[SupportedLanguage] = Field(
        description="Languages touched in this diff"
    )
    historical_matches: list[ReviewCommentRecord] = Field(
        description="Historical review comments ranked by match_score"
    )
    ponytail_findings: list[PonytailFinding] = Field(
        default_factory=list,
        description="Automated ponytail over-engineering audit findings",
    )
    domain_findings: list[DomainFinding] = Field(
        default_factory=list, description="Automated UFS-Chem domain rule findings"
    )
    suggested_patches: list[CodePatch] = Field(
        default_factory=list,
        description="All machine-applicable code patches from automated rules",
    )
    diff_text: str | None = Field(
        default=None,
        description="Normalized unified diff text of the evaluated changes",
    )
    critical_summary_prompt: str = Field(
        description="Instructions for the client LLM on synthesizing these findings into the critical summary"
    )


class GeneratePatchInput(BaseModel):
    """Input payload for generate_patch MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patches: list[CodePatch] = Field(
        description="List of code patches to assemble into a unified diff"
    )
