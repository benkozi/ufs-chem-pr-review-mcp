"""Orchestrator for syncing GitHub PR reviews and diff follow-ups into SQLite."""

import re
from datetime import datetime, timezone
from typing import Any

from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.ingest.classifier import (
    classify_comment,
    detect_language,
)
from ufs_chem_pr_review_mcp.ingest.client import GitHubClient
from ufs_chem_pr_review_mcp.ingest.diff_tracker import determine_followup_status
from ufs_chem_pr_review_mcp.logs import get_logger

logger = get_logger("ingest.syncer")

LINE_EXTRACT_RE = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _parse_patch_lines(patch_text: str) -> tuple[list[int], list[int]]:
    """Parse added and deleted line numbers from a unified diff hunk."""
    added: list[int] = []
    deleted: list[int] = []
    curr_new = 0
    curr_old = 0

    for line in patch_text.splitlines():
        if line.startswith("@@"):
            m = LINE_EXTRACT_RE.search(line)
            if m:
                curr_old = int(m.group(1))
                curr_new = int(m.group(2))
        elif line.startswith("+"):
            added.append(curr_new)
            curr_new += 1
        elif line.startswith("-"):
            deleted.append(curr_old)
            curr_old += 1
        else:
            curr_old += 1
            curr_new += 1

    return added, deleted


def sync_repository(
    client: GitHubClient,
    db: ReviewDatabase,
    repo_name: str,
    repo_url: str,
    default_branch: str = "main",
) -> int:
    """Synchronize pull requests, comments, and follow-up diffs for a repository into local SQLite.

    Returns the count of synced review comments.
    """
    logger.info(f"Starting review synchronization for {repo_name}")
    db.upsert_repository(name=repo_name, url=repo_url, default_branch=default_branch)

    prs = client.get_pull_requests(repo_name, state="all")
    total_comments_synced = 0

    for pr in prs:
        pr_number = pr["number"]
        title = pr.get("title", "")
        author_login = pr.get("user", {}).get("login", "unknown")
        state = pr.get("state", "open")
        base_sha = pr.get("base", {}).get("sha", "")
        head_sha = pr.get("head", {}).get("sha", "")
        created_at = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
        merged_at = (
            datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            if pr.get("merged_at")
            else None
        )

        db.upsert_pull_request(
            repo_name=repo_name,
            pr_number=pr_number,
            title=title,
            author_login=author_login,
            state=state,
            base_sha=base_sha,
            head_sha=head_sha,
            created_at=created_at,
            updated_at=updated_at,
            merged_at=merged_at,
        )

        comments = client.get_pr_comments(repo_name, pr_number)
        if not comments:
            continue

        # Fetch commits to evaluate follow-up code changes
        commits_meta = client.get_pr_commits(repo_name, pr_number)
        parsed_commits: list[dict[str, Any]] = []

        for c in commits_meta:
            c_sha = c["sha"]
            c_date_str = c.get("commit", {}).get("committer", {}).get("date") or c.get(
                "commit", {}
            ).get("author", {}).get("date")
            c_date = (
                datetime.fromisoformat(c_date_str.replace("Z", "+00:00"))
                if c_date_str
                else created_at
            )
            parsed_commits.append({"sha": c_sha, "date": c_date, "patches": None})

        for comment in comments:
            c_created_str = comment["created_at"]
            c_created = datetime.fromisoformat(c_created_str.replace("Z", "+00:00"))
            path = comment.get("path", "")
            body = comment.get("body", "")
            comment_line = comment.get("line") or comment.get("original_line")

            # Collect subsequent commit patches
            subsequent_patches: list[dict[str, Any]] = []
            for pc in parsed_commits:
                if pc["date"] > c_created:
                    if pc["patches"] is None:
                        # Lazy fetch commit file detail
                        try:
                            detail = client.get_commit_detail(repo_name, pc["sha"])
                            patches_list: list[dict[str, Any]] = []
                            for f in detail.get("files", []):
                                p_text = f.get("patch", "")
                                if p_text:
                                    add, delete = _parse_patch_lines(p_text)
                                    patches_list.append(
                                        {
                                            "path": f.get("filename"),
                                            "added_lines": add,
                                            "deleted_lines": delete,
                                        }
                                    )
                            pc["patches"] = patches_list
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch commit {pc['sha']} detail: {e}"
                            )
                            pc["patches"] = []

                    subsequent_patches.extend(pc["patches"])

            followup_status, has_followup = determine_followup_status(
                comment_path=path,
                comment_line=comment_line,
                subsequent_patches=subsequent_patches,
            )

            language = detect_language(path)
            category, criticality = classify_comment(
                body, has_diff_followup=has_followup
            )

            db.insert_review_comment(
                repo_name=repo_name,
                pr_number=pr_number,
                comment_node_id=str(comment.get("node_id") or comment.get("id")),
                author_login=comment.get("user", {}).get("login", "unknown"),
                author_association=comment.get("author_association", "NONE"),
                body=body,
                path=path,
                line=comment.get("line"),
                original_line=comment.get("original_line"),
                start_line=comment.get("start_line"),
                side=comment.get("side", "RIGHT"),
                diff_hunk=comment.get("diff_hunk"),
                language=language,
                category=category,
                criticality=criticality,
                has_diff_followup=has_followup,
                diff_followup_status=followup_status,
                created_at=c_created,
                updated_at=datetime.fromisoformat(
                    comment["updated_at"].replace("Z", "+00:00")
                ),
            )
            total_comments_synced += 1

    db.update_repo_synced_at(repo_name, datetime.now(timezone.utc))
    logger.info(
        f"Completed synchronization for {repo_name}: {total_comments_synced} comments stored."
    )
    return total_comments_synced
