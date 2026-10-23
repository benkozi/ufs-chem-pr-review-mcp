"""SQLite DDL schema, FTS5 virtual tables, and migrations."""

import sqlite3

CURRENT_SCHEMA_VERSION = 1

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        url TEXT NOT NULL,
        default_branch TEXT NOT NULL DEFAULT 'main',
        last_synced_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS pull_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
        pr_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        author_login TEXT NOT NULL,
        state TEXT NOT NULL,
        base_sha TEXT NOT NULL,
        head_sha TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        merged_at TEXT,
        indexed_at TEXT NOT NULL,
        UNIQUE(repo_id, pr_number)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS review_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pr_id INTEGER NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
        comment_node_id TEXT NOT NULL UNIQUE,
        author_login TEXT NOT NULL,
        author_association TEXT NOT NULL,
        body TEXT NOT NULL,
        path TEXT NOT NULL,
        line INTEGER,
        original_line INTEGER,
        start_line INTEGER,
        side TEXT NOT NULL DEFAULT 'RIGHT',
        diff_hunk TEXT,
        language TEXT NOT NULL,
        category TEXT NOT NULL,
        criticality INTEGER NOT NULL CHECK(criticality BETWEEN 1 AND 5),
        has_diff_followup INTEGER NOT NULL CHECK(has_diff_followup IN (0, 1)),
        diff_followup_status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        indexed_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_comments_path ON review_comments(path);",
    "CREATE INDEX IF NOT EXISTS idx_comments_language ON review_comments(language);",
    "CREATE INDEX IF NOT EXISTS idx_comments_category ON review_comments(category);",
    "CREATE INDEX IF NOT EXISTS idx_comments_criticality ON review_comments(criticality);",
    "CREATE INDEX IF NOT EXISTS idx_comments_has_diff_followup ON review_comments(has_diff_followup);",
    "CREATE INDEX IF NOT EXISTS idx_comments_created_at ON review_comments(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_comments_author ON review_comments(author_login);",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS comments_fts USING fts5(
        body,
        path,
        diff_hunk,
        content='review_comments',
        content_rowid='id'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS comments_ai AFTER INSERT ON review_comments BEGIN
        INSERT INTO comments_fts(rowid, body, path, diff_hunk) VALUES (new.id, new.body, new.path, new.diff_hunk);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS comments_ad AFTER DELETE ON review_comments BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, path, diff_hunk) VALUES('delete', old.id, old.body, old.path, old.diff_hunk);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS comments_au AFTER UPDATE ON review_comments BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, path, diff_hunk) VALUES('delete', old.id, old.body, old.path, old.diff_hunk);
        INSERT INTO comments_fts(rowid, body, path, diff_hunk) VALUES (new.id, new.body, new.path, new.diff_hunk);
    END;
    """,
]


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schema, foreign keys, and WAL journal mode."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("PRAGMA user_version;")
    current_version = cursor.fetchone()[0]

    if current_version < CURRENT_SCHEMA_VERSION:
        for stmt in DDL_STATEMENTS:
            cursor.execute(stmt)
        cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
        conn.commit()
