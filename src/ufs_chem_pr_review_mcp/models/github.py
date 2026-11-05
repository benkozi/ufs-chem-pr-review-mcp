"""GitHub Review API payload, PR URL parser, comment, and validity models."""

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

_PR_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/)?([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)(?:/pull/|#)(\d+)(?:/.*)?$"
)


class PrUrlComponents(BaseModel):
    """Parsed components from a GitHub pull request URL."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owner: str = Field(
        description="GitHub repository owner or organization, e.g. 'ufs-community'"
    )
    repo: str = Field(description="GitHub repository name, e.g. 'CATChem'")
    pr_number: int = Field(ge=1, description="Pull request number")

    @property
    def full_repo(self) -> str:
        """Full repository name in owner/repo format."""
        return f"{self.owner}/{self.repo}"


def parse_github_pr_url(url: str) -> PrUrlComponents:
    """Parse a GitHub Pull Request URL or shorthand identifier into PrUrlComponents.

    Supports:
    - https://github.com/owner/repo/pull/123
    - https://github.com/owner/repo/pull/123/files
    - https://github.com/owner/repo/pull/123/
    - owner/repo#123
    - owner/repo/pull/123

    Raises:
        ValueError: If the string is not a valid GitHub PR URL or shorthand.
    """
    clean_url = url.strip()
    match = _PR_URL_PATTERN.match(clean_url)
    if not match:
        raise ValueError(f"Cannot parse GitHub PR URL: {url!r}")

    owner, repo, pr_str = match.groups()
    pr_number = int(pr_str)
    if pr_number < 1:
        raise ValueError(
            f"Cannot parse GitHub PR URL (PR number must be >= 1): {url!r}"
        )

    return PrUrlComponents(owner=owner, repo=repo, pr_number=pr_number)


class CommentValidity(str, Enum):
    """Technical and domain validity assessment for an existing PR comment."""

    VALID = "valid"
    INVALID = "invalid"
    OUTDATED = "outdated"
    PARTIALLY_VALID = "partially_valid"


class ExistingPrComment(BaseModel):
    """An existing comment on a pull request (diff inline, conversation thread, or pending draft)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    comment_id: int | None = Field(
        default=None, description="GitHub comment ID if persisted"
    )
    author: str = Field(description="GitHub username of the comment author")
    body: str = Field(description="Comment text body")
    created_at: str | None = Field(
        default=None, description="ISO8601 creation timestamp"
    )
    path: str | None = Field(
        default=None, description="Relative file path if inline comment"
    )
    line: int | None = Field(default=None, description="Line number if inline comment")
    side: str = Field(default="RIGHT", description="Diff side: LEFT or RIGHT")
    is_pending: bool = Field(
        default=False, description="True if unsubmitted draft review comment"
    )
    review_id: int | None = Field(
        default=None, description="Associated review ID if part of a formal review"
    )
    in_reply_to_id: int | None = Field(
        default=None, description="Parent comment ID if a threaded reply"
    )


class ExistingCommentEvaluation(BaseModel):
    """AI evaluation of the technical validity and resolution status of an existing PR comment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    comment: ExistingPrComment = Field(
        description="The existing comment under evaluation"
    )
    validity: CommentValidity = Field(
        description="Assessment of validity: valid, invalid, outdated, or partially_valid"
    )
    validity_rationale: str = Field(
        description="Detailed explanation verifying or refuting the comment claim against code logic and domain physics"
    )
    is_addressed: bool = Field(
        description="True if the author has pushed code addressing the comment"
    )
    resolution_notes: str | None = Field(
        default=None,
        description="Description of the author's resolution or why it remains open",
    )
    suggested_action: str = Field(
        description="Actionable advice: DISMISS_FALSE_POSITIVE, RESOLVE_WITH_PATCH, EXPAND_DRAFT, or MAINTAIN_STATUS_QUO"
    )


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
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="First line in the diff for a multi-line comment (must be < line)",
    )
    start_side: str | None = Field(
        default=None,
        description="The side of the diff for start_line: LEFT or RIGHT",
    )
    body: str = Field(description="The markdown body of the comment")
    suggested_change: str | None = Field(
        default=None,
        exclude=True,
        description="Exact code suggestion rendered as ```suggestion\\n{suggested_change}\\n``` for 1-click GitHub PR commit",
    )

    def rendered_body(self) -> str:
        """Return the comment body, appending a GitHub suggestion block if suggested_change is provided."""
        if not self.suggested_change:
            return self.body
        suggestion_block = f"```suggestion\n{self.suggested_change.rstrip()}\n```"
        if suggestion_block in self.body:
            return self.body.strip()
        if self.body.strip():
            return f"{self.body.strip()}\n\n{suggestion_block}"
        return suggestion_block


class GitHubReviewPayload(BaseModel):
    """Pending-only payload for GitHub REST API: POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews.

    By omitting the ``event`` field (and forbidding extra fields), this payload is
    structurally guaranteed to only ever create a PENDING draft review on GitHub.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    commit_id: str | None = Field(
        default=None,
        description="Optional SHA of the commit that needs a review",
    )
    body: str = Field(description="The overarching critical review summary in Markdown")
    comments: list[GitHubInlineComment] = Field(
        default_factory=list, description="List of inline comments to post"
    )

    def to_gh_api_json(self) -> str:
        """Serialize as a pending-only GitHub REST API review JSON payload."""
        rendered_comments = [
            c.model_copy(update={"body": c.rendered_body()}) for c in self.comments
        ]
        normalized = self.model_copy(update={"comments": rendered_comments})
        return normalized.model_dump_json(indent=2, exclude_none=True)
