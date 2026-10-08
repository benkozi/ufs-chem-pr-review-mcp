"""Data Access Layer (DAL) for UFS-Chem PR review comments and repositories."""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ufs_chem_pr_review_mcp.db.schema import init_db
from ufs_chem_pr_review_mcp.logs import get_logger
from ufs_chem_pr_review_mcp.models.common import (
    DiffFollowUpStatus,
    ReviewCategory,
    SupportedLanguage,
)
from ufs_chem_pr_review_mcp.models.review import (
    PullRequestRecord,
    ReviewCommentRecord,
)

logger = get_logger("db.repository")

# Regex to extract alphanumeric tokens and identifiers for safe FTS5 queries
TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_]+")


def sanitize_fts_query(query: str) -> str:
    """Sanitize user or LLM search query for SQLite FTS5 to avoid syntax errors.

    Strips dangerous characters and operators, wraps tokens in double quotes,
    joined by implicit AND.
    """
    tokens = TOKEN_PATTERN.findall(query)
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens)


def compute_match_score(
    comment_path: str,
    diff_path: str,
    comment_lang: SupportedLanguage,
    diff_lang: SupportedLanguage,
    has_diff_followup: bool,
    criticality: int,
    bm25_rank: float = 0.0,
) -> float:
    """Compute deterministic relevance score of a historical comment against an evaluated diff file."""
    score = 0.0

    # Path proximity
    c_path = Path(comment_path)
    d_path = Path(diff_path)
    if c_path == d_path:
        score += 50.0
    elif c_path.parent == d_path.parent and c_path.parent != Path("."):
        score += 25.0

    # Language match
    if comment_lang == diff_lang and diff_lang != SupportedLanguage.UNKNOWN:
        score += 10.0

    # Actionable follow-up bonus
    if has_diff_followup:
        score += 20.0

    # Criticality multiplier (1 to 5)
    score += 5.0 * criticality

    # FTS5 BM25 rank contribution (BM25 is negative in SQLite FTS5, lower/more negative is better)
    if bm25_rank < 0:
        score += min(15.0, abs(bm25_rank))

    return round(score, 2)


class ReviewDatabase:
    """Database client for managing historical PR reviews in SQLite."""

    def __init__(self, db_path: Path, read_only: bool = False) -> None:
        self.db_path = db_path
        self.read_only = read_only
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Create and return a new SQLite database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if self.read_only:
            conn.execute("PRAGMA query_only = ON;")
        return conn

    def init_schema(self) -> None:
        """Initialize database tables and triggers if not already present."""
        conn = self.get_connection()
        try:
            init_db(conn)
        finally:
            conn.close()

    def upsert_repository(
        self, name: str, url: str, default_branch: str = "main"
    ) -> int:
        """Insert or update a repository record."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO repositories (name, url, default_branch, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    url = excluded.url,
                    default_branch = excluded.default_branch,
                    updated_at = excluded.updated_at
                RETURNING id;
                """,
                (name, url, default_branch, now, now),
            )
            row = cursor.fetchone()
            conn.commit()
            return int(row["id"])
        finally:
            conn.close()

    def get_repository(self, name: str) -> dict[str, str] | None:
        """Fetch repository details by name."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories WHERE name = ?;", (name,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "url": str(row["url"]),
                "default_branch": str(row["default_branch"]),
                "last_synced_at": str(row["last_synced_at"])
                if row["last_synced_at"]
                else "",
            }
        finally:
            conn.close()

    def list_repositories(self) -> list[dict[str, str]]:
        """List all tracked repositories."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM repositories ORDER BY name ASC;")
            rows = cursor.fetchall()
            return [
                {
                    "name": str(r["name"]),
                    "url": str(r["url"]),
                    "default_branch": str(r["default_branch"]),
                    "last_synced_at": str(r["last_synced_at"])
                    if r["last_synced_at"]
                    else "",
                }
                for r in rows
            ]
        finally:
            conn.close()

    def update_repo_synced_at(self, name: str, synced_at: datetime) -> None:
        """Update last_synced_at timestamp for a repository."""
        conn = self.get_connection()
        try:
            conn.execute(
                "UPDATE repositories SET last_synced_at = ?, updated_at = ? WHERE name = ?;",
                (synced_at.isoformat(), synced_at.isoformat(), name),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        title: str,
        author_login: str,
        state: str,
        base_sha: str,
        head_sha: str,
        created_at: datetime,
        updated_at: datetime,
        merged_at: datetime | None = None,
    ) -> int:
        """Insert or update a pull request record."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM repositories WHERE name = ?;", (repo_name,))
            repo_row = cursor.fetchone()
            if not repo_row:
                raise ValueError(f"Repository not registered: {repo_name}")
            repo_id = repo_row["id"]

            cursor.execute(
                """
                INSERT INTO pull_requests (
                    repo_id, pr_number, title, author_login, state,
                    base_sha, head_sha, created_at, updated_at, merged_at, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id, pr_number) DO UPDATE SET
                    title = excluded.title,
                    author_login = excluded.author_login,
                    state = excluded.state,
                    base_sha = excluded.base_sha,
                    head_sha = excluded.head_sha,
                    updated_at = excluded.updated_at,
                    merged_at = excluded.merged_at,
                    indexed_at = excluded.indexed_at
                RETURNING id;
                """,
                (
                    repo_id,
                    pr_number,
                    title,
                    author_login,
                    state,
                    base_sha,
                    head_sha,
                    created_at.isoformat(),
                    updated_at.isoformat(),
                    merged_at.isoformat() if merged_at else None,
                    now,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            return int(row["id"])
        finally:
            conn.close()

    def get_pull_request(
        self, repo_name: str, pr_number: int
    ) -> PullRequestRecord | None:
        """Fetch a pull request record by repo name and number."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pr.*, r.name as repo_name
                FROM pull_requests pr
                JOIN repositories r ON pr.repo_id = r.id
                WHERE r.name = ? AND pr.pr_number = ?;
                """,
                (repo_name, pr_number),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return PullRequestRecord(
                id=int(row["id"]),
                repo_name=str(row["repo_name"]),
                pr_number=int(row["pr_number"]),
                title=str(row["title"]),
                author_login=str(row["author_login"]),
                state=str(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                merged_at=datetime.fromisoformat(row["merged_at"])
                if row["merged_at"]
                else None,
                base_sha=str(row["base_sha"]),
                head_sha=str(row["head_sha"]),
                indexed_at=datetime.fromisoformat(row["indexed_at"]),
            )
        finally:
            conn.close()

    def insert_review_comment(
        self,
        repo_name: str,
        pr_number: int,
        comment_node_id: str,
        author_login: str,
        author_association: str,
        body: str,
        path: str,
        line: int | None,
        original_line: int | None,
        start_line: int | None,
        side: str,
        diff_hunk: str | None,
        language: SupportedLanguage,
        category: ReviewCategory,
        criticality: int,
        has_diff_followup: bool,
        diff_followup_status: DiffFollowUpStatus,
        created_at: datetime,
        updated_at: datetime,
    ) -> int:
        """Insert or replace a review comment record."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pr.id FROM pull_requests pr
                JOIN repositories r ON pr.repo_id = r.id
                WHERE r.name = ? AND pr.pr_number = ?;
                """,
                (repo_name, pr_number),
            )
            pr_row = cursor.fetchone()
            if not pr_row:
                raise ValueError(
                    f"Pull request not registered: {repo_name}#{pr_number}"
                )
            pr_id = pr_row["id"]

            cursor.execute(
                """
                INSERT INTO review_comments (
                    pr_id, comment_node_id, author_login, author_association,
                    body, path, line, original_line, start_line, side, diff_hunk,
                    language, category, criticality, has_diff_followup,
                    diff_followup_status, created_at, updated_at, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(comment_node_id) DO UPDATE SET
                    body = excluded.body,
                    line = excluded.line,
                    has_diff_followup = excluded.has_diff_followup,
                    diff_followup_status = excluded.diff_followup_status,
                    updated_at = excluded.updated_at,
                    indexed_at = excluded.indexed_at
                RETURNING id;
                """,
                (
                    pr_id,
                    comment_node_id,
                    author_login,
                    author_association,
                    body,
                    path,
                    line,
                    original_line,
                    start_line,
                    side,
                    diff_hunk,
                    language.value,
                    category.value,
                    criticality,
                    1 if has_diff_followup else 0,
                    diff_followup_status.value,
                    created_at.isoformat(),
                    updated_at.isoformat(),
                    now,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            return int(row["id"])
        finally:
            conn.close()

    def get_review_comments_for_pr(
        self, repo_name: str, pr_number: int
    ) -> list[ReviewCommentRecord]:
        """Fetch all review comments associated with a pull request."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT rc.*, r.name as repo_name, pr.pr_number
                FROM review_comments rc
                JOIN pull_requests pr ON rc.pr_id = pr.id
                JOIN repositories r ON pr.repo_id = r.id
                WHERE r.name = ? AND pr.pr_number = ?
                ORDER BY rc.created_at ASC;
                """,
                (repo_name, pr_number),
            )
            rows = cursor.fetchall()
            return [self._row_to_comment_record(r) for r in rows]
        finally:
            conn.close()

    def search_review_comments(
        self,
        query: str,
        repo: str | None = None,
        language: SupportedLanguage | None = None,
        category: ReviewCategory | None = None,
        min_criticality: int | None = None,
        has_diff_followup_only: bool = False,
        limit: int = 10,
    ) -> list[ReviewCommentRecord]:
        """Perform full-text search across historical review comments with optional metadata filters."""
        sanitized = sanitize_fts_query(query)
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            params: list[Any] = []
            clauses = ["1=1"]

            if sanitized != '""':
                clauses.append(
                    "rc.id IN (SELECT rowid FROM comments_fts WHERE comments_fts MATCH ?)"
                )
                params.append(sanitized)

            if repo:
                clauses.append("r.name = ?")
                params.append(repo)
            if language:
                clauses.append("rc.language = ?")
                params.append(language.value)
            if category:
                clauses.append("rc.category = ?")
                params.append(category.value)
            if min_criticality:
                clauses.append("rc.criticality >= ?")
                params.append(min_criticality)
            if has_diff_followup_only:
                clauses.append("rc.has_diff_followup = 1")

            params.append(limit)
            where_sql = " AND ".join(clauses)

            sql = f"""
                SELECT rc.*, r.name as repo_name, pr.pr_number
                FROM review_comments rc
                JOIN pull_requests pr ON rc.pr_id = pr.id
                JOIN repositories r ON pr.repo_id = r.id
                WHERE {where_sql}
                ORDER BY rc.has_diff_followup DESC, rc.criticality DESC, rc.created_at DESC
                LIMIT ?;
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_comment_record(r) for r in rows]
        finally:
            conn.close()

    def query_relevant_comments(
        self,
        target_repo: str,
        touched_files: list[str],
        languages: list[SupportedLanguage],
        identifiers: list[str] | None = None,
        limit: int = 15,
    ) -> list[ReviewCommentRecord]:
        """Retrieve and rank historical comments matching touched files, languages, and identifiers."""
        # Build candidate search pool across touched files and identifiers
        query_parts: list[str] = []
        for f in touched_files:
            query_parts.append(Path(f).stem)
        if identifiers:
            query_parts.extend(identifiers[:10])

        search_query = " ".join(query_parts) if query_parts else "review"
        candidates = self.search_review_comments(query=search_query, limit=50)

        # Also pull exact path matches directly even if FTS didn't hit
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if touched_files:
                placeholders = ",".join("?" for _ in touched_files)
                sql = f"""
                    SELECT rc.*, r.name as repo_name, pr.pr_number
                    FROM review_comments rc
                    JOIN pull_requests pr ON rc.pr_id = pr.id
                    JOIN repositories r ON pr.repo_id = r.id
                    WHERE rc.path IN ({placeholders})
                    ORDER BY rc.criticality DESC
                    LIMIT 25;
                """
                cursor.execute(sql, touched_files)
                for r in cursor.fetchall():
                    rec = self._row_to_comment_record(r)
                    if not any(c.id == rec.id for c in candidates):
                        candidates.append(rec)
        finally:
            conn.close()

        # Score candidates
        scored: list[ReviewCommentRecord] = []
        primary_lang = languages[0] if languages else SupportedLanguage.UNKNOWN

        for cand in candidates:
            best_score = 0.0
            for tf in touched_files:
                s = compute_match_score(
                    comment_path=cand.path,
                    diff_path=tf,
                    comment_lang=cand.language,
                    diff_lang=primary_lang,
                    has_diff_followup=cand.has_diff_followup,
                    criticality=cand.criticality,
                )
                if s > best_score:
                    best_score = s

            # Model is frozen, so create updated instance
            scored.append(cand.model_copy(update={"match_score": best_score}))

        scored.sort(key=lambda x: x.match_score or 0.0, reverse=True)
        return scored[:limit]

    def get_repo_stats(self, repo_name: str) -> dict[str, Any]:
        """Aggregate summary review metrics for a repository."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT pr.id) as total_prs,
                    COUNT(rc.id) as total_comments,
                    SUM(CASE WHEN rc.has_diff_followup = 1 THEN 1 ELSE 0 END) as diff_followup_count
                FROM repositories r
                LEFT JOIN pull_requests pr ON pr.repo_id = r.id
                LEFT JOIN review_comments rc ON rc.pr_id = pr.id
                WHERE r.name = ?;
                """,
                (repo_name,),
            )
            agg = cursor.fetchone()
            total_prs = int(agg["total_prs"]) if agg and agg["total_prs"] else 0
            total_comments = (
                int(agg["total_comments"]) if agg and agg["total_comments"] else 0
            )
            diff_followup_count = (
                int(agg["diff_followup_count"])
                if agg and agg["diff_followup_count"]
                else 0
            )
            diff_rate = (
                round(diff_followup_count / total_comments, 2)
                if total_comments > 0
                else 0.0
            )

            # Top reviewers
            cursor.execute(
                """
                SELECT rc.author_login, COUNT(rc.id) as cnt
                FROM review_comments rc
                JOIN pull_requests pr ON rc.pr_id = pr.id
                JOIN repositories r ON pr.repo_id = r.id
                WHERE r.name = ?
                GROUP BY rc.author_login
                ORDER BY cnt DESC
                LIMIT 5;
                """,
                (repo_name,),
            )
            top_reviewers = [
                {"author_login": str(r["author_login"]), "count": int(r["cnt"])}
                for r in cursor.fetchall()
            ]

            return {
                "repo_name": repo_name,
                "total_prs": total_prs,
                "total_comments": total_comments,
                "diff_followup_count": diff_followup_count,
                "diff_followup_rate": diff_rate,
                "top_reviewers": top_reviewers,
            }
        finally:
            conn.close()

    def _row_to_comment_record(self, row: sqlite3.Row) -> ReviewCommentRecord:
        """Convert a database row into a ReviewCommentRecord instance."""
        return ReviewCommentRecord(
            id=int(row["id"]),
            comment_node_id=str(row["comment_node_id"]),
            repo_name=str(row["repo_name"]),
            pr_number=int(row["pr_number"]),
            author_login=str(row["author_login"]),
            author_association=str(row["author_association"]),
            body=str(row["body"]),
            path=str(row["path"]),
            line=int(row["line"]) if row["line"] is not None else None,
            original_line=int(row["original_line"])
            if row["original_line"] is not None
            else None,
            start_line=int(row["start_line"])
            if row["start_line"] is not None
            else None,
            side=str(row["side"]),
            diff_hunk=str(row["diff_hunk"]) if row["diff_hunk"] is not None else None,
            language=SupportedLanguage(str(row["language"])),
            category=ReviewCategory(str(row["category"])),
            criticality=int(row["criticality"]),
            has_diff_followup=bool(row["has_diff_followup"]),
            diff_followup_status=DiffFollowUpStatus(str(row["diff_followup_status"])),
            match_score=None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            indexed_at=datetime.fromisoformat(row["indexed_at"]),
        )
