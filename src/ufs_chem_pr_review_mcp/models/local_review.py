"""Pydantic schemas and parsers for recording local review comments and managing reconciliation."""

import hashlib
import html
import re
import subprocess
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ufs_chem_pr_review_mcp.models.common import ReviewCategory, SupportedLanguage
from ufs_chem_pr_review_mcp.models.github import (
    GitHubInlineComment,
    GitHubReviewPayload,
)


class FindingSeverity(str, Enum):
    """Review finding severity levels matching review-pr skill standard."""

    P0_BLOCKER = "P0"
    P1_MAJOR = "P1"
    P2_MODERATE = "P2"
    P3_MINOR = "P3"

    @property
    def label(self) -> str:
        """Human-readable priority label."""
        labels = {
            FindingSeverity.P0_BLOCKER: "Blocker",
            FindingSeverity.P1_MAJOR: "Major",
            FindingSeverity.P2_MODERATE: "Moderate",
            FindingSeverity.P3_MINOR: "Minor",
        }
        return labels[self]

    @property
    def default_criticality(self) -> int:
        """Map severity level to database criticality integer (1 to 5)."""
        mapping = {
            FindingSeverity.P0_BLOCKER: 5,
            FindingSeverity.P1_MAJOR: 4,
            FindingSeverity.P2_MODERATE: 3,
            FindingSeverity.P3_MINOR: 1,
        }
        return mapping[self]


class LocalReviewCommentInput(BaseModel):
    """Input payload for a single review comment synthesized by the deep-dive review assistant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(
        description="Relative file path within the repository where the finding applies"
    )
    line: int | None = Field(
        default=None,
        ge=1,
        description="Line number in the new code (None for top-level or file-level comment)",
    )
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="Starting line number for multi-line comment ranges",
    )
    body: str = Field(
        description="Markdown text of the review comment explaining the issue, rationale, and recommendation"
    )
    category: ReviewCategory = Field(
        default=ReviewCategory.CORRECTNESS,
        description="Review taxonomy category (e.g. physics_chemistry, over_engineering, style_standards, performance)",
    )
    severity: FindingSeverity = Field(
        default=FindingSeverity.P2_MODERATE,
        description="Prioritized severity ranking: P0 (Blocker), P1 (Major), P2 (Moderate/Ponytail), P3 (Nit)",
    )
    criticality: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Explicit criticality (1-5). If None, inferred automatically from severity tier",
    )
    language: SupportedLanguage = Field(
        default=SupportedLanguage.UNKNOWN,
        description="Programming language of the target file (Fortran, C++, Python, Bash, etc.)",
    )
    diff_hunk: str | None = Field(
        default=None,
        description="Relevant unified diff hunk context associated with this comment",
    )
    suggested_change: str | None = Field(
        default=None,
        description="Exact replacement code snippet suitable for a GitHub suggestion block",
    )
    author_login: str = Field(
        default="antigravity-review",
        description="Author attribution for the comment (e.g. 'antigravity-review', 'user')",
    )

    def resolved_criticality(self) -> int:
        """Return explicit criticality or fall back to severity mapping."""
        return (
            self.criticality
            if self.criticality is not None
            else self.severity.default_criticality
        )


class RecordReviewCommentsInput(BaseModel):
    """Input payload for record_review_comments MCP tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str | None = Field(
        default=None,
        description="Target repository in owner/repo format, e.g. 'ufs-community/CATChem'",
    )
    pr_number: int | None = Field(
        default=None,
        ge=1,
        description="Pull request number",
    )
    pr_url: str | None = Field(
        default=None,
        description="Full GitHub PR URL (e.g. 'https://github.com/ufs-community/CATChem/pull/123')",
    )
    comments: list[LocalReviewCommentInput] = Field(
        default_factory=list,
        description="List of structured review comments to insert",
    )
    review_file_path: str | None = Field(
        default=None,
        description="Path to a markdown review report file from which findings will be extracted automatically",
    )
    markdown_text: str | None = Field(
        default=None,
        description="Raw markdown review report content from which findings will be extracted automatically",
    )
    payload_output_path: str | None = Field(
        default=None,
        description="Optional file path where the pending-only review_payload.json for gh api will be written",
    )
    source_tag: str = Field(
        default="agent-deep-dive",
        description="Source identifier tag indicating review provenance",
    )

    @model_validator(mode="after")
    def validate_inputs(self) -> "RecordReviewCommentsInput":
        if not self.pr_url and not (self.repo and self.pr_number):
            raise ValueError("Must provide either pr_url or both repo and pr_number.")
        if not self.comments and not self.review_file_path and not self.markdown_text:
            raise ValueError(
                "Must provide at least one of: comments, review_file_path, or markdown_text."
            )
        return self


class RecordedCommentSummary(BaseModel):
    """Summary of an individual comment recorded in the database."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    comment_node_id: str = Field(description="Deterministic synthetic node ID")
    path: str = Field(description="File path of the finding")
    line: int | None = Field(default=None, description="Line number of the finding")
    category: ReviewCategory = Field(description="Assigned category")
    severity: FindingSeverity = Field(
        description="Assigned severity tier (P0, P1, P2, P3)"
    )
    priority_label: str = Field(
        description="Human-readable priority label: Blocker, Major, Moderate, Minor"
    )
    criticality: int = Field(description="Assigned criticality score (1-5)")
    status: str = Field(description="'inserted' or 'updated'")


class RecordReviewCommentsResponse(BaseModel):
    """Output confirmation payload from record_review_comments tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str = Field(description="Target repository evaluated")
    pr_number: int = Field(description="Target PR number")
    total_received: int = Field(
        description="Total candidate findings parsed or received"
    )
    inserted_count: int = Field(
        description="Number of new comments inserted into database"
    )
    updated_count: int = Field(
        description="Number of existing comments updated in place"
    )
    db_path: str = Field(description="Absolute path to the SQLite review database")
    review_payload_path: str | None = Field(
        default=None,
        description="Absolute path to the generated pending-only review_payload.json file for gh api",
    )
    review_body_path: str | None = Field(
        default=None,
        description="Absolute path to the generated Markdown file containing the review body for copy-paste submission",
    )
    recorded_comments: list[RecordedCommentSummary] = Field(
        default_factory=list,
        description="List of recorded comments and their synthetic node IDs",
    )


class ReconciliationStats(BaseModel):
    """Statistics summarizing reconciliation between local synthetic comments and incoming GitHub comments."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str = Field(description="Repository reconciled")
    pr_number: int = Field(description="PR number reconciled")
    local_comments_found: int = Field(
        description="Total local synthetic comments present before sync"
    )
    reconciled_count: int = Field(
        description="Count of local synthetic comments superseded by official GitHub comments"
    )
    retained_local_count: int = Field(
        description="Count of local comments retained (unposted on GitHub)"
    )


def generate_synthetic_node_id(
    repo_name: str,
    pr_number: int,
    path: str,
    line: int | None,
    category: str,
    body: str,
) -> str:
    """Generate a deterministic synthetic comment_node_id for a local review finding.

    Format: local-review:{repo}#{pr_number}:{path}:{line}:{fingerprint}
    where fingerprint is a 12-character SHA-256 hex digest of category and body.
    """
    norm_path = path.strip().replace("\\", "/")
    norm_line = str(line) if line is not None else "0"
    content_key = f"{category}:{body.strip()}".encode("utf-8")
    fingerprint = hashlib.sha256(content_key).hexdigest()[:12]
    return f"local-review:{repo_name}#{pr_number}:{norm_path}:{norm_line}:{fingerprint}"


def parse_review_markdown_findings(
    markdown_text: str,
) -> list[LocalReviewCommentInput]:
    """Parse prioritized findings and suggestions from a review-pr markdown report.

    Extracts:
    - Section 5 items: ### [P0] Title, Location, Problem, Rationale, ```suggestion``` blocks.
    - Categorizes severity, maps file path, extracts line numbers, and builds structured comments.
    """
    from ufs_chem_pr_review_mcp.ingest.classifier import detect_language

    comments: list[LocalReviewCommentInput] = []

    pattern = re.compile(
        r"###\s*`?\[(P[0-3])\]`?\s*([^\n]+)\n"
        r"(?:.*?- \*\*Location\*\*:\s*\[?`?([^:`\n\]]+)(?::|#L)?(\d+)?(?:-L?(\d+))?`?\]?[^\n]*\n)?"
        r"(.*?)(?=(?:\n###\s*`?\[P[0-3]\]`?|\n##\s|\Z))",
        re.DOTALL,
    )
    post_loc_pattern = re.compile(
        r"- \*\*Recommended Post Location\*\*:\s*[^\n]*?(?::|#L|lines?\s+`?)(\d+)(?:-L?(\d+))?",
        re.IGNORECASE,
    )

    for m in pattern.finditer(markdown_text):
        sev_str, title, raw_path, raw_line, raw_end_line, content = m.groups()
        severity = FindingSeverity(sev_str)
        path = (
            raw_path.strip().strip("`").replace("file://", "").split("#")[0].strip()
            if raw_path
            else "unknown"
        )
        # Strip leading slashes if file:/// was used without relative path prefix
        if path.startswith("/"):
            path = path.lstrip("/")

        first_line = int(raw_line) if raw_line else None
        end_line = int(raw_end_line) if raw_end_line else None

        post_match = post_loc_pattern.search(content)
        if post_match:
            first_line = int(post_match.group(1))
            end_line = int(post_match.group(2)) if post_match.group(2) else None

        if first_line is not None and end_line is not None and end_line > first_line:
            start_line: int | None = first_line
            line: int | None = end_line
        else:
            start_line = None
            line = first_line

        cleaned_content = re.sub(
            r"^\s*- \*\*(?:Recommended Post Location|Tag)\*\*:[^\n]*\n?",
            "",
            content,
            flags=re.MULTILINE,
        )
        cleaned_content = re.sub(r"\n+---\s*\Z", "", cleaned_content).strip()

        sugg_match = re.search(r"```suggestion\n(.*?)\n```", cleaned_content, re.DOTALL)
        suggested_change = sugg_match.group(1) if sugg_match else None

        category = _infer_finding_category(title, cleaned_content)
        lang = detect_language(path)

        body = f"**[{severity.value} - {severity.label}] {title.strip()}**\n\n{cleaned_content}"
        comments.append(
            LocalReviewCommentInput(
                path=path,
                line=line,
                start_line=start_line,
                body=body,
                category=category,
                severity=severity,
                language=lang,
                suggested_change=suggested_change,
                author_login="antigravity-review",
            )
        )

    return comments


def parse_diff_right_ranges(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Extract valid right-side (new file) line ranges per file from a unified diff."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            ranges.setdefault(current_file, [])
        elif raw_line.startswith("@@ ") and current_file:
            hm = hunk_re.match(raw_line)
            if hm:
                start = int(hm.group(1))
                count = int(hm.group(2)) if hm.group(2) is not None else 1
                if count > 0:
                    ranges[current_file].append((start, start + count - 1))

    return ranges


def _range_in_hunks(
    start_line: int, end_line: int, hunks: list[tuple[int, int]]
) -> bool:
    """Return True if [start_line, end_line] lies inside at least one diff hunk."""
    return any(h_start <= start_line and end_line <= h_end for h_start, h_end in hunks)


def _format_out_of_diff_note(loc_label: str, rendered_text: str) -> str:
    """Format an out-of-diff finding with a collapsible details block under its [P*] heading."""
    parts = rendered_text.split("\n\n", 1)
    first_line = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    if re.match(r"^\*\*\[P\d+\b", first_line) and rest:
        heading = html.escape(first_line.strip("* ").strip())
        heading_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", heading)
        loc_html = f"<code>{html.escape(loc_label)}</code>"
        return (
            "<details>\n"
            f"<summary><b>{heading_html}</b> ({loc_html})</summary>\n\n"
            f"**Location:** `{loc_label}`\n\n"
            f"{rest}\n\n"
            "</details>"
        )
    prefix = f"#### `{loc_label}`" if loc_label != "General" else "#### General"
    return f"{prefix}\n\n{rendered_text}"


def get_mcp_server_commit_hash() -> str:
    """Return the git commit hash of the ufs-chem-pr-review-mcp repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[3],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def build_pending_review_payload(
    comments: list[LocalReviewCommentInput],
    diff_text: str | None = None,
    commit_id: str | None = None,
    mcp_commit_hash: str | None = None,
) -> GitHubReviewPayload:
    """Build a pending-only GitHubReviewPayload (no event field) from review findings.

    If ``diff_text`` is provided, findings whose file or line range falls outside
    the PR's right-side diff hunks are automatically folded into the top-level
    pending review summary body so ``gh api`` never rejects the POST with HTTP 422.
    """
    mcp_commit = mcp_commit_hash or get_mcp_server_commit_hash()
    diff_ranges = parse_diff_right_ranges(diff_text) if diff_text else {}
    has_diff_filter = bool(diff_ranges)

    inline_comments: list[GitHubInlineComment] = []
    out_of_diff_notes: list[str] = []

    for c in comments:
        temp_comment = GitHubInlineComment(
            path=c.path,
            line=c.line or 1,
            body=c.body,
            suggested_change=c.suggested_change,
        )
        rendered_text = temp_comment.rendered_body()

        if c.line is None or c.path == "unknown":
            loc_label = c.path if c.path != "unknown" else "General"
            out_of_diff_notes.append(_format_out_of_diff_note(loc_label, rendered_text))
            continue

        s_line = (
            c.start_line
            if (c.start_line is not None and c.start_line < c.line)
            else None
        )

        if has_diff_filter:
            file_hunks = diff_ranges.get(c.path, [])
            eff_start = s_line if s_line is not None else c.line
            if _range_in_hunks(eff_start, c.line, file_hunks):
                inline_comments.append(
                    GitHubInlineComment(
                        path=c.path,
                        line=c.line,
                        side="RIGHT",
                        start_line=s_line,
                        start_side="RIGHT" if s_line is not None else None,
                        body=rendered_text,
                    )
                )
            elif c.suggested_change is None and _range_in_hunks(
                c.line, c.line, file_hunks
            ):
                inline_comments.append(
                    GitHubInlineComment(
                        path=c.path,
                        line=c.line,
                        side="RIGHT",
                        body=rendered_text,
                    )
                )
            else:
                loc_str = (
                    f"{c.path}:{s_line}-{c.line}"
                    if s_line is not None
                    else f"{c.path}:{c.line}"
                )
                out_of_diff_notes.append(
                    _format_out_of_diff_note(loc_str, rendered_text)
                )
        else:
            inline_comments.append(
                GitHubInlineComment(
                    path=c.path,
                    line=c.line,
                    side="RIGHT",
                    start_line=s_line,
                    start_side="RIGHT" if s_line is not None else None,
                    body=rendered_text,
                )
            )

    commit_ref = (
        f"[{mcp_commit[:8]}](https://github.com/benkozi/ufs-chem-pr-review-mcp/commit/{mcp_commit})"
        if mcp_commit != "unknown"
        else "unknown"
    )
    summary_parts = [
        f"Machine-generated comments by [ufs-chem-pr-review-mcp](https://github.com/benkozi/ufs-chem-pr-review-mcp) @ {commit_ref}\n\n"
        f"Pending code review ({len(inline_comments)} inline diff comment(s), "
        f"{len(out_of_diff_notes)} file/out-of-diff finding(s))."
    ]
    if out_of_diff_notes:
        summary_parts.append(
            "### File-Level & Out-of-Diff Findings\n\n"
            + "\n\n---\n\n".join(out_of_diff_notes)
        )

    return GitHubReviewPayload(
        commit_id=commit_id,
        body="\n\n".join(summary_parts),
        comments=inline_comments,
    )


def _infer_finding_category(title: str, content: str) -> ReviewCategory:
    """Infer ReviewCategory from finding title and text content."""
    combined = f"{title} {content}".lower()
    if any(
        k in combined
        for k in [
            "chemistry",
            "molar",
            "mixing ratio",
            "reaction",
            "photolysis",
            "emission",
            "physics",
        ]
    ):
        return ReviewCategory.CHEMISTRY_PHYSICS
    if any(
        k in combined
        for k in [
            "esmf",
            "nuopc",
            "fieldbundle",
        ]
    ):
        return ReviewCategory.ESMF_NUOPC
    if any(
        k in combined
        for k in [
            "leak",
            "allocation",
            "stat=",
            "errmsg",
            "esmf_log",
            "crash",
            "segfault",
            "allocate",
            "uninitialized",
            "deadlock",
        ]
    ):
        return ReviewCategory.CORRECTNESS
    if any(
        k in combined
        for k in [
            "ponytail",
            "yagni",
            "dead code",
            "removable",
            "shrink",
            "delete",
            "wrapper",
        ]
    ):
        return ReviewCategory.OVERENGINEERING

    if any(
        k in combined
        for k in [
            "kind",
            "standard",
            "pure",
            "openmp",
            "raii",
            "formatting",
            "flang",
            "typo",
            "naming",
        ]
    ):
        return ReviewCategory.STYLE_DOCS
    return ReviewCategory.CORRECTNESS
