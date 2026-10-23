"""Database pruning routines for enforcing data retention and size limits."""

import sqlite3
from datetime import datetime, timedelta, timezone

from ufs_chem_pr_review_mcp.logs import get_logger

logger = get_logger("db.pruning")


def prune_database(
    conn: sqlite3.Connection,
    retention_days: int | None = None,
    max_records_per_repo: int | None = None,
) -> int:
    """Prune historical pull requests and cascade delete associated comments.

    Returns the count of deleted pull request records.
    """
    total_deleted = 0
    cursor = conn.cursor()

    # Prune by retention days
    if retention_days is not None and retention_days > 0:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()
        cursor.execute(
            """
            DELETE FROM pull_requests
            WHERE updated_at < ?;
            """,
            (cutoff,),
        )
        deleted = cursor.rowcount
        total_deleted += max(0, deleted)
        logger.info(
            f"Pruned {deleted} pull requests older than {retention_days} days (cutoff: {cutoff})"
        )

    # Prune by maximum pull requests per repository
    if max_records_per_repo is not None and max_records_per_repo > 0:
        cursor.execute("SELECT id FROM repositories;")
        repos = cursor.fetchall()
        for r in repos:
            repo_id = r[0]
            cursor.execute(
                """
                DELETE FROM pull_requests
                WHERE id IN (
                    SELECT id FROM pull_requests
                    WHERE repo_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                );
                """,
                (repo_id, max_records_per_repo),
            )
            deleted = cursor.rowcount
            total_deleted += max(0, deleted)
            if deleted > 0:
                logger.info(
                    f"Pruned {deleted} overflow pull requests for repo id {repo_id}"
                )

    conn.commit()
    return total_deleted
