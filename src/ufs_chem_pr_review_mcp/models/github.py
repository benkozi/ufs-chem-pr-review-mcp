"""GitHub Review API payload and inline comment models."""

from pydantic import BaseModel, ConfigDict, Field

from ufs_chem_pr_review_mcp.models.common import ReviewEvent


class GitHubInlineComment(BaseModel):
    """Inline review comment posted on a pull request diff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(
        description="The relative path to the file that necessitates a comment"
    )
    line: int = Field(description="The line index in the diff to comment on")
    side: str = Field(
        default="RIGHT", description="The side of the diff to comment on: LEFT or RIGHT"
    )
    body: str = Field(description="The markdown body of the comment")
    suggested_change: str | None = Field(
        default=None,
        description="Exact code suggestion rendered as ```suggestion\\n{suggested_change}\\n``` for 1-click GitHub PR commit",
    )

    def rendered_body(self) -> str:
        """Return the comment body, appending a GitHub suggestion block if suggested_change is provided."""
        if not self.suggested_change:
            return self.body
        suggestion_block = f"```suggestion\n{self.suggested_change.rstrip()}\n```"
        if self.body.strip():
            return f"{self.body.strip()}\n\n{suggestion_block}"
        return suggestion_block


class GitHubReviewPayload(BaseModel):
    """Payload compatible with GitHub REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: ReviewEvent = Field(
        description="The review action: COMMENT, REQUEST_CHANGES, or APPROVE"
    )
    body: str = Field(description="The overarching critical review summary in Markdown")
    comments: list[GitHubInlineComment] = Field(
        default_factory=list, description="List of inline comments to post"
    )
