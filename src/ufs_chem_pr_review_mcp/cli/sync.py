"""CLI entrypoint: ufs-chem-pr-review-sync."""

import argparse
import sys
from pathlib import Path

from ufs_chem_pr_review_mcp.config import Settings, load_repositories_config
from ufs_chem_pr_review_mcp.db.pruning import prune_database
from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.ingest.client import GitHubClient
from ufs_chem_pr_review_mcp.ingest.syncer import sync_repository
from ufs_chem_pr_review_mcp.logs import configure_logging, get_logger

logger = get_logger("cli.sync")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for repository review sync and pruning."""
    parser = argparse.ArgumentParser(
        prog="ufs-chem-pr-review-sync",
        description="Sync historical PR reviews from UFS-Chem GitHub repositories into local SQLite database.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/repositories.yaml"),
        help="Path to repositories configuration YAML file.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database file (overrides settings).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Specific repository name to sync (e.g. ufs-community/CATChem).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Prune records older than specified days.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Prune repository records to max pull requests.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR.",
    )

    args = parser.parse_args(argv)
    configure_logging(level=args.log_level)
    settings = Settings()

    cfg_path = args.config
    if not cfg_path.exists():
        logger.error(f"Configuration file not found: {cfg_path}")
        sys.exit(1)

    try:
        repo_file = load_repositories_config(cfg_path)
    except Exception as e:
        logger.error(f"Error loading repository configuration: {e}")
        sys.exit(1)

    db_path = args.db or settings.db_path
    db = ReviewDatabase(db_path)
    db.init_schema()

    client = GitHubClient(token=settings.github_token)

    try:
        repos_to_sync = [
            r
            for r in repo_file.repositories
            if r.enabled and (args.repo is None or r.name == args.repo)
        ]

        if not repos_to_sync:
            logger.warning("No matching repositories found to sync.")

        for r in repos_to_sync:
            try:
                sync_repository(
                    client=client,
                    db=db,
                    repo_name=r.name,
                    repo_url=r.url,
                    default_branch=r.default_branch,
                )
            except Exception as e:
                logger.error(f"Failed to sync repository {r.name}: {e}")

        # Run pruning if specified
        retention = args.retention_days or settings.retention_days
        if retention or args.max_records:
            conn = db.get_connection()
            try:
                pruned = prune_database(
                    conn=conn,
                    retention_days=retention,
                    max_records_per_repo=args.max_records,
                )
                logger.info(
                    f"Database pruning finished. Total records pruned: {pruned}"
                )
            finally:
                conn.close()

    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
