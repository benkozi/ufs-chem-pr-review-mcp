"""Data models for stored pull requests and classified historical review comments."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ufs_chem_pr_review_mcp.models.common import (
    DiffFollowUpStatus,
    ReviewCategory,
    SupportedLanguage,
)


class ReviewCommentRecord(BaseModel):
    """Normalized historical review comment indexed in local SQLite storage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(description="Internal primary key of the comment record")
    comment_node_id: str = Field(
        description="GitHub GraphQL node ID or REST ID of the comment"
    )
    repo_name: str = Field(
        description="Full repository name, e.g. ufs-community/CATChem"
    )
    pr_number: int = Field(description="Pull request number")
    author_login: str = Field(
        description="GitHub username of the reviewer who created the comment"
    )
    author_association: str = Field(
        description="Author association: OWNER, MEMBER, COLLABORATOR, CONTRIBUTOR, NONE"
    )
    body: str = Field(description="Raw markdown body of the review comment")
    path: str = Field(
        description="File path in the repository that the comment references"
    )
    line: int | None = Field(
        default=None, description="Line number in the diff that the comment references"
    )
    original_line: int | None = Field(
        default=None, description="Original line number in the diff hunk"
    )
    start_line: int | None = Field(
        default=None, description="Start line for multi-line review comments"
    )
    side: str = Field(
        default="RIGHT",
        description="Diff side: LEFT (base deletions) or RIGHT (head additions)",
    )
    diff_hunk: str | None = Field(
        default=None, description="Surrounding diff hunk context for the comment"
    )
    language: SupportedLanguage = Field(
        description="Detected programming language of the commented file"
    )
    category: ReviewCategory = Field(
        description="Primary classified category of the review comment"
    )
    criticality: int = Field(
        ge=1,
        le=5,
        description="Ranking for how critical the catch was (1=nit, 5=blocker)",
    )
    has_diff_followup: bool = Field(
        description="Whether a follow-up commit modified the target code after this comment"
    )
    diff_followup_status: DiffFollowUpStatus = Field(
        description="Detailed resolution status of the diff follow-up"
    )
    match_score: float | None = Field(
        default=None,
        description="Deterministic relevance score when matched against an evaluated diff",
    )
    created_at: datetime = Field(
        description="ISO 8601 creation timestamp of the review comment on GitHub"
    )
    updated_at: datetime = Field(
        description="ISO 8601 update timestamp of the review comment on GitHub"
    )
    indexed_at: datetime = Field(
        description="ISO 8601 timestamp when this record was stored in the local SQLite DB"
    )


class PullRequestRecord(BaseModel):
    """Metadata for an indexed pull request in the local repository database."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int = Field(description="Internal primary key of the pull request")
    repo_name: str = Field(description="Full repository name")
    pr_number: int = Field(description="Pull request number")
    title: str = Field(description="Title of the pull request")
    author_login: str = Field(description="Author login of the PR creator")
    state: str = Field(description="PR state: open, closed, or merged")
    created_at: datetime = Field(description="PR creation timestamp")
    updated_at: datetime = Field(description="PR update timestamp")
    merged_at: datetime | None = Field(
        default=None, description="PR merged timestamp, if merged"
    )
    base_sha: str = Field(description="Base commit SHA of the PR")
    head_sha: str = Field(description="Head commit SHA of the PR")
    indexed_at: datetime = Field(description="Timestamp when indexed locally")
