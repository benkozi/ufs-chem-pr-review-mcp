"""Local Model Context Protocol (MCP) server for UFS-Chem code reviews."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ufs_chem_pr_review_mcp.config import Settings
from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.ingest.classifier import detect_language
from ufs_chem_pr_review_mcp.ingest.client import GitHubApiError, GitHubClient
from ufs_chem_pr_review_mcp.ingest.diff_tracker import normalize_fortran_continuations
from ufs_chem_pr_review_mcp.logs import configure_logging, get_logger
from ufs_chem_pr_review_mcp.models.common import (
    OutputFormat,
    ReviewCategory,
    ReviewEvent,
    ReviewMode,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.models.github import (
    GitHubInlineComment,
    GitHubReviewPayload,
)
from ufs_chem_pr_review_mcp.models.mcp_tools import (
    DomainFinding,
    PonytailFinding,
    ReviewContextResponse,
)
from ufs_chem_pr_review_mcp.models.patch import (
    CodePatch,
    build_unified_diff_patch,
)
from ufs_chem_pr_review_mcp.rules.ponytail import evaluate_ponytail_rules
from ufs_chem_pr_review_mcp.rules.ufs_chem import evaluate_ufs_chem_rules

logger = get_logger("server")

READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)


def _split_diff_by_file(diff_text: str) -> dict[str, str]:
    """Split unified diff text into a mapping of file_path -> file_diff_text."""
    files: dict[str, str] = {}
    current_file: str | None = None
    current_lines: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_file and current_lines:
                files[current_file] = "\n".join(current_lines)
            m = re.search(r"b/(.+)$", line)
            current_file = m.group(1) if m else "unknown"
            current_lines = [line]
        else:
            if current_file:
                current_lines.append(line)

    if current_file and current_lines:
        files[current_file] = "\n".join(current_lines)

    return files


def _build_context_response(
    diff_text: str,
    target_repo: str,
    pr_number: int | None,
    review_mode: ReviewMode,
    include_ponytail: bool,
    max_context_comments: int,
    db: ReviewDatabase,
) -> ReviewContextResponse:
    """Analyze diff, run rules, and retrieve historical context."""
    file_diffs = _split_diff_by_file(diff_text)
    touched_files = list(file_diffs.keys())

    detected_languages: set[SupportedLanguage] = set()
    ponytail_findings: list[PonytailFinding] = []
    domain_findings: list[DomainFinding] = []
    suggested_patches: list[CodePatch] = []

    for fpath, fdiff in file_diffs.items():
        lang = detect_language(fpath)
        detected_languages.add(lang)

        # Normalize Fortran continuations if applicable
        eval_diff = fdiff
        if lang == SupportedLanguage.FORTRAN:
            norm_lines, _ = normalize_fortran_continuations(fdiff.splitlines())
            eval_diff = "\n".join(norm_lines)

        # Run Ponytail audit
        if include_ponytail:
            pt_list = evaluate_ponytail_rules(fpath, eval_diff, lang)
            ponytail_findings.extend(pt_list)
            for pt in pt_list:
                if pt.patch:
                    suggested_patches.append(pt.patch)

        # Run UFS-Chem domain rules
        dom_list = evaluate_ufs_chem_rules(fpath, eval_diff, lang)
        domain_findings.extend(dom_list)
        for dom in dom_list:
            if dom.patch:
                suggested_patches.append(dom.patch)

    # Retrieve historical comments
    history = db.query_relevant_comments(
        target_repo=target_repo,
        touched_files=touched_files,
        languages=list(detected_languages),
        limit=max_context_comments,
    )

    prompt = (
        "Please review this pull request diff using the historical review context, "
        "automated ponytail over-engineering findings, and domain correctness rules provided. "
        "Produce a Critical Summary covering high-risk issues, lines removable, and inline suggestions."
    )

    return ReviewContextResponse(
        repo=target_repo,
        pr_number=pr_number,
        review_mode=review_mode,
        touched_files=touched_files,
        detected_languages=list(detected_languages),
        historical_matches=history,
        ponytail_findings=ponytail_findings,
        domain_findings=domain_findings,
        suggested_patches=suggested_patches,
        diff_text=diff_text,
        critical_summary_prompt=prompt,
    )


def _render_markdown(ctx: ReviewContextResponse) -> str:
    """Render a structured markdown code review."""
    lines: list[str] = []

    if ctx.review_mode in (ReviewMode.SUMMARY_AND_INLINE, ReviewMode.SUMMARY_ONLY):
        lines.append(
            f"## Code Review Summary: `{ctx.repo}`"
            + (f" (PR #{ctx.pr_number})" if ctx.pr_number else "")
        )
        lines.append("")
        lines.append("### Critical Summary")
        if not ctx.domain_findings and not ctx.ponytail_findings:
            lines.append(
                "No critical issues or domain violations identified. Code looks clean."
            )
        else:
            lines.append(
                f"- **Domain / Correctness Issues**: {len(ctx.domain_findings)}"
            )
            lines.append(
                f"- **Over-engineering Catches**: {len(ctx.ponytail_findings)}"
            )

        lines.append("")
        lines.append("### Ponytail Audit")
        if not ctx.ponytail_findings:
            lines.append("> Lean already. Ship.")
        else:
            total_saved = sum(f.lines_saved_estimate for f in ctx.ponytail_findings)
            lines.append(f"> Net lines removable estimate: **{total_saved} lines**")
            for pf in ctx.ponytail_findings:
                lines.append(
                    f"- `L{pf.line_number}` `{pf.file_path}`: **[{pf.tag}]** {pf.what_to_cut}. {pf.replacement}."
                )
        lines.append("")

    if ctx.review_mode in (ReviewMode.SUMMARY_AND_INLINE, ReviewMode.INLINE_ONLY):
        if ctx.domain_findings:
            lines.append("### Domain Findings & Inline Recommendations")
            for df in ctx.domain_findings:
                lines.append(
                    f"- `{df.file_path}:{df.line_number}` **[{df.rule_name}]** (Criticality: {df.criticality}/5)"
                )
                lines.append(f"  {df.explanation}")
                if df.replacement_code:
                    lines.append(f"  ```suggestion\n  {df.replacement_code}\n  ```")
            lines.append("")

        if ctx.suggested_patches:
            lines.append("### Machine-Applicable Patches")
            lines.append("Run `git apply` with the following unified diff:")
            lines.append("```diff")
            patch_res = build_unified_diff_patch(ctx.suggested_patches)
            lines.append(patch_res.patch_text.strip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def _render_github_json(ctx: ReviewContextResponse) -> str:
    """Render GitHub Review API JSON payload."""
    comments: list[GitHubInlineComment] = []

    for df in ctx.domain_findings:
        comments.append(
            GitHubInlineComment(
                path=df.file_path,
                line=df.line_number,
                side="RIGHT",
                body=df.explanation,
                suggested_change=df.replacement_code,
            )
        )

    for pf in ctx.ponytail_findings:
        comments.append(
            GitHubInlineComment(
                path=pf.file_path,
                line=pf.line_number,
                side="RIGHT",
                body=f"[{pf.tag}] {pf.what_to_cut}. {pf.replacement}.",
                suggested_change=pf.replacement_code
                if pf.replacement_code is not None
                else None,
            )
        )

    max_crit = max([df.criticality for df in ctx.domain_findings], default=1)
    event = ReviewEvent.REQUEST_CHANGES if max_crit >= 4 else ReviewEvent.COMMENT

    summary_text = _render_markdown(ctx)
    payload = GitHubReviewPayload(
        event=event,
        body=summary_text,
        comments=comments,
    )
    return payload.model_dump_json(indent=2)


def _format_context_response(ctx: ReviewContextResponse, output_format: str) -> str:
    """Format ReviewContextResponse into specified OutputFormat (patch, github_json, or markdown)."""
    fmt = OutputFormat(output_format)
    if fmt == OutputFormat.PATCH:
        return build_unified_diff_patch(ctx.suggested_patches).patch_text
    if fmt == OutputFormat.GITHUB_JSON:
        return _render_github_json(ctx)
    return _render_markdown(ctx)


def create_mcp_server(db_path: Path | None = None) -> FastMCP:
    """Initialize and configure the FastMCP server instance."""
    settings = Settings()
    active_db_path = db_path or settings.db_path

    # Configure logging strictly to sys.stderr to protect stdout JSON-RPC transport
    configure_logging(level=settings.log_level, stream=sys.stderr)

    db = ReviewDatabase(active_db_path)
    db.init_schema()

    mcp = FastMCP("ufs-chem-pr-review-mcp")

    # 1. evaluate_diff
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Evaluates a git diff text. Matches historical review comments, runs ponytail and domain audits, and outputs structured review context, markdown, or patches.",
    )
    def evaluate_diff(
        diff_text: str,
        target_repo: str = "ufs-community/CATChem",
        output_format: str = "markdown",
        review_mode: str = "summary_and_inline",
        include_ponytail_audit: bool = True,
        max_context_comments: int = 15,
    ) -> str:
        ctx = _build_context_response(
            diff_text=diff_text,
            target_repo=target_repo,
            pr_number=None,
            review_mode=ReviewMode(review_mode),
            include_ponytail=include_ponytail_audit,
            max_context_comments=max_context_comments,
            db=db,
        )
        return _format_context_response(ctx, output_format)

    # 2. evaluate_pr
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Evaluates a GitHub pull request in a UFS-Chem repository. Parses the PR diff, retrieves matching historical review comments, runs ponytail and domain audits, and outputs structured review context.",
    )
    def evaluate_pr(
        repo: str,
        pr_number: int,
        output_format: str = "markdown",
        review_mode: str = "summary_and_inline",
        include_ponytail_audit: bool = True,
        max_context_comments: int = 15,
    ) -> str:
        client = GitHubClient(token=settings.github_token)
        try:
            diff_text = client.get_pr_diff(repo, pr_number)
        except GitHubApiError as e:
            return json.dumps(
                {"error": str(e), "message": "Failed to fetch PR diff from GitHub."}
            )
        finally:
            client.close()

        ctx = _build_context_response(
            diff_text=diff_text,
            target_repo=repo,
            pr_number=pr_number,
            review_mode=ReviewMode(review_mode),
            include_ponytail=include_ponytail_audit,
            max_context_comments=max_context_comments,
            db=db,
        )
        return _format_context_response(ctx, output_format)

    # 3. search_review_history
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Performs full-text search across historical review comments and threads with metadata filters.",
    )
    def search_review_history(
        query: str,
        repo: str | None = None,
        language: str | None = None,
        category: str | None = None,
        min_criticality: int | None = None,
        has_diff_followup_only: bool = False,
        limit: int = 10,
    ) -> str:
        results = db.search_review_comments(
            query=query,
            repo=repo,
            language=SupportedLanguage(language) if language else None,
            category=ReviewCategory(category) if category else None,
            min_criticality=min_criticality,
            has_diff_followup_only=has_diff_followup_only,
            limit=limit,
        )
        return json.dumps([r.model_dump(mode="json") for r in results], indent=2)

    # 4. get_repo_review_stats
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Retrieves review statistics for a UFS-Chem repository (total PRs, comments, top reviewers, followup acceptance rate).",
    )
    def get_repo_review_stats(repo: str) -> str:
        stats = db.get_repo_stats(repo)
        return json.dumps(stats, indent=2)

    # 5. format_review_output
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Helper tool that converts structured findings into GitHub Review JSON, Markdown, or unified diff patch.",
    )
    def format_review_output(
        findings: list[dict[str, Any]],
        critical_summary: str,
        suggested_patches: list[dict[str, Any]] | None = None,
        output_format: str = "markdown",
        review_mode: str = "summary_and_inline",
    ) -> str:
        patches = [CodePatch.model_validate(p) for p in (suggested_patches or [])]
        fmt = OutputFormat(output_format)

        if fmt == OutputFormat.PATCH:
            # If explicit patches provided, use them; otherwise extract from findings
            if not patches:
                for f in findings:
                    if f.get("suggested_change"):
                        patches.append(
                            CodePatch(
                                file_path=f["path"],
                                start_line=f["line"],
                                end_line=f["line"],
                                original_code="",
                                replacement_code=f["suggested_change"] + "\n",
                                unified_hunk=f"@@ -{f['line']},1 +{f['line']},1 @@\n+{f['suggested_change']}\n",
                            )
                        )
            return build_unified_diff_patch(patches).patch_text

        if fmt == OutputFormat.GITHUB_JSON:
            comments = [
                GitHubInlineComment(
                    path=f["path"],
                    line=f["line"],
                    side=f.get("side", "RIGHT"),
                    body=f.get("body", ""),
                    suggested_change=f.get("suggested_change"),
                )
                for f in findings
            ]
            # Replace bodies with rendered_body for GitHub suggestion blocks
            rendered_comments = [
                c.model_copy(update={"body": c.rendered_body()}) for c in comments
            ]
            payload = GitHubReviewPayload(
                event=ReviewEvent.COMMENT,
                body=critical_summary,
                comments=rendered_comments,
            )
            return payload.model_dump_json(indent=2)

        # Markdown output
        lines = [f"## Code Review Summary\n\n{critical_summary}\n"]
        for f in findings:
            lines.append(f"- `{f.get('path')}:{f.get('line')}`: {f.get('body')}")
            if f.get("suggested_change"):
                lines.append(f"  ```suggestion\n  {f['suggested_change']}\n  ```")
        return "\n".join(lines)

    # 6. generate_patch
    @mcp.tool(
        annotations=READ_ONLY_ANNOTATIONS,
        description="Assembles structured CodePatch objects into a single unified diff patch string compatible with git apply.",
    )
    def generate_patch(patches: list[dict[str, Any]]) -> str:
        patch_objs = [CodePatch.model_validate(p) for p in patches]
        res = build_unified_diff_patch(patch_objs)
        return res.model_dump_json(indent=2)

    # Resources
    @mcp.resource("ufs-chem://repositories")
    def get_repositories_resource() -> str:
        """JSON listing of all tracked UFS-Chem repositories."""
        repos = db.list_repositories()
        return json.dumps(repos, indent=2)

    @mcp.resource("ufs-chem://guidelines/{category}")
    def get_guidelines_resource(category: str) -> str:
        """Markdown guidelines and common reviewer pitfalls for specific review categories."""
        guidelines = {
            "chemistry_physics": (
                "# Chemistry & Physics Review Guidelines\n\n"
                "- Check mixing ratio normalization: ppm/ppb requires conversion by molecular weight ratio (M_spec / M_air).\n"
                "- Verify mass conservation across photolysis and reaction kinetics.\n"
                "- Ensure standard temperature and pressure (STP) versus ambient pressure state corrections."
            ),
            "esmf_nuopc": (
                "# ESMF & NUOPC Cap Guidelines\n\n"
                "- Check that ESMF_StateGet return code (rc) is checked with ESMF_LogFoundError.\n"
                "- Ensure all advertised fields are realized before state coupling.\n"
                "- Verify clock and timestep coordination."
            ),
            "ponytail": (
                "# Ponytail Over-engineering Guidelines\n\n"
                "- Delete dead code and commented-out snippets.\n"
                "- Favor stdlib / native over unnecessary third-party packages or custom reimplementations.\n"
                "- Collapse scalar loops into modern array syntax where appropriate."
            ),
        }
        return guidelines.get(
            category,
            f"# Guidelines for {category}\n\nNo specific guidelines registered.",
        )

    # Prompts
    @mcp.prompt()
    def review_pr(
        repo: str,
        pr_number: str,
        output_format: str = "markdown",
        review_mode: str = "summary_and_inline",
    ) -> str:
        return (
            f"Please conduct an in-depth code review for {repo} PR #{pr_number}.\n"
            f"1. Call `evaluate_pr(repo='{repo}', pr_number={pr_number}, output_format='{output_format}', review_mode='{review_mode}')`.\n"
            "2. Audit for over-engineering (ponytail findings: delete, stdlib, native, yagni, shrink).\n"
            "3. Verify atmospheric chemistry physical unit consistency, molecular weights, and ESMF return checks.\n"
            "4. Provide the critical review summary and format inline suggestions using ```suggestion blocks or patch hunks so the user can immediately apply them."
        )

    return mcp


def main() -> None:
    """Entry point for running the MCP server over STDIO."""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
