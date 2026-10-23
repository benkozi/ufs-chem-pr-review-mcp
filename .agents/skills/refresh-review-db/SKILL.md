---
name: refresh-review-db
description: >-
  Sync and update the historical PR review database (data/ufs_chem_reviews.sqlite3)
  across UFS-Chem repositories using ufs-chem-pr-review-sync. Use this skill whenever
  the user asks to update, refresh, or sync the review database, or before running
  reviews on recently updated repositories.
---

# `refresh-review-db` Runbook

Automate historical PR review synchronization and database updates for the `ufs-chem-pr-review-mcp` service.

## Workflow Execution Steps

### 1. Step 1: Preflight GitHub Authentication Check
Verify GitHub credentials prior to launching the synchronizer:
```bash
gh auth status
```
- If authenticated via GitHub CLI, `ufs-chem-pr-review-sync` automatically extracts the token via `gh auth token`.
- If unauthenticated, verify if `UFS_CHEM_GITHUB_TOKEN` or `GITHUB_TOKEN` exists in the environment.
- If no credentials exist, stop and notify the user:
  > "Please authenticate with GitHub CLI via `gh auth login` or export `GITHUB_TOKEN`."

### 2. Step 2: Configuration & Parameter Assessment
- Verify `config/repositories.yaml` is present and review configured repositories (`CATChem`, `CECE`, `HELM`, etc.).
- Parse user arguments:
  - If a specific repository was requested (e.g., `ufs-community/CATChem`), use `--repo <repo_name>`.
  - If retention parameters were provided, pass `--retention-days <days>` or `--max-records <records>`.
  - Otherwise, run across all configured repositories.

### 3. Step 3: Execute Sync
Execute the synchronization CLI command:
```bash
uv run ufs-chem-pr-review-sync [--repo <repo_name>] [--log-level INFO]
```
The synchronizer performs:
1. Retrieval of pull requests, commits, and review comments via GitHub REST API.
2. Code patch and diff follow-up status resolution (`code_modified`, `discussion_only`, etc.).
3. Full-text search (FTS5) indexing and metadata classification.
4. Retention policy enforcement and database vacuuming.

### 4. Step 4: Verification & Database Health Check
Verify that the database at `data/ufs_chem_reviews.sqlite3` was updated:
```bash
python3 -c "
import sqlite3
con = sqlite3.connect('data/ufs_chem_reviews.sqlite3')
cur = con.cursor()
prs = cur.execute('SELECT count(*) FROM pull_requests').fetchone()[0]
comments = cur.execute('SELECT count(*) FROM review_comments').fetchone()[0]
latest = cur.execute('SELECT max(created_at) FROM review_comments').fetchone()[0]
print(f'Indexed PRs: {prs}, Indexed Comments: {comments}, Latest Review: {latest}')
"
```

### 5. Step 5: Present Summary to User
Report the sync results to the user:
- Repositories synchronized.
- Total pull requests and review comments indexed.
- Timestamp of most recent review in the database.
- Any API rate limit warnings.
