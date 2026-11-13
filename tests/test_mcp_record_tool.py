"""Tests for record_review_comments tool on the FastMCP server."""

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.models.common import ReviewCategory
from ufs_chem_pr_review_mcp.models.local_review import FindingSeverity
from ufs_chem_pr_review_mcp.server import create_mcp_server


def _tool_text(res: Any) -> str:
    """Extract string text from FastMCP tool call result."""
    content_list, _ = res
    item = content_list[0]
    return getattr(item, "text", str(item))


@pytest.fixture
def mcp_app(tmp_path: Path) -> FastMCP:
    db_path = tmp_path / "test_reviews.sqlite3"
    db = ReviewDatabase(db_path)
    db.init_schema()
    return create_mcp_server(db_path=db_path)


@pytest.mark.asyncio
async def test_record_review_comments_missing_target(mcp_app: FastMCP) -> None:
    res = await mcp_app.call_tool(
        "record_review_comments",
        {"comments": [{"path": "a.F90", "body": "test"}]},
    )
    data = json.loads(_tool_text(res))
    assert "error" in data
    assert "Must provide pr_url or both repo and pr_number" in data["message"]


@pytest.mark.asyncio
async def test_record_review_comments_invalid_url(mcp_app: FastMCP) -> None:
    res = await mcp_app.call_tool(
        "record_review_comments",
        {"pr_url": "not-a-valid-url", "comments": [{"path": "a.F90", "body": "test"}]},
    )
    data = json.loads(_tool_text(res))
    assert "error" in data
    assert "Invalid pr_url" in data["message"]


@pytest.mark.asyncio
async def test_record_review_comments_no_findings(mcp_app: FastMCP) -> None:
    res = await mcp_app.call_tool(
        "record_review_comments",
        {"repo": "ufs-community/CATChem", "pr_number": 123},
    )
    data = json.loads(_tool_text(res))
    assert "error" in data
    assert "No findings" in data["error"]


@pytest.mark.asyncio
async def test_record_review_comments_nonexistent_file(mcp_app: FastMCP) -> None:
    res = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 123,
            "review_file_path": "/nonexistent/path/review.md",
        },
    )
    data = json.loads(_tool_text(res))
    assert "error" in data
    assert "No findings" in data["error"]


@pytest.mark.asyncio
async def test_record_review_comments_with_structured_comments(
    mcp_app: FastMCP, tmp_path: Path
) -> None:
    comments = [
        {
            "path": "chem/rates.F90",
            "line": 42,
            "body": "Missing molecular weight factor in rate expression",
            "category": ReviewCategory.CHEMISTRY_PHYSICS.value,
            "severity": FindingSeverity.P0_BLOCKER.value,
            "suggested_change": "rate = 1.0_rk * temp * mw_scale",
        },
        {
            "path": "chem/utils.F90",
            "line": 15,
            "body": "Delete redundant single-caller wrapper",
            "category": ReviewCategory.OVERENGINEERING.value,
            "severity": FindingSeverity.P2_MODERATE.value,
        },
    ]

    res = await mcp_app.call_tool(
        "record_review_comments",
        {
            "pr_url": "https://github.com/ufs-community/CATChem/pull/123",
            "comments": comments,
        },
    )
    data = json.loads(_tool_text(res))
    assert data["repo"] == "ufs-community/CATChem"
    assert data["pr_number"] == 123
    assert data["total_received"] == 2
    assert data["inserted_count"] == 2
    assert data["updated_count"] == 0
    assert len(data["recorded_comments"]) == 2
    assert data["recorded_comments"][0]["priority_label"] == "Blocker"
    assert data["recorded_comments"][0]["criticality"] == 5
    assert data["recorded_comments"][1]["priority_label"] == "Moderate"
    assert data["recorded_comments"][1]["criticality"] == 3


@pytest.mark.asyncio
async def test_record_review_comments_with_markdown_file(
    mcp_app: FastMCP, tmp_path: Path
) -> None:
    md_path = tmp_path / "review-123.md"
    md_path.write_text(
        """# Pull Request Review: [ufs-community/CATChem#123]

## 5. Detailed Findings & Machine-Applicable Suggestions

### [P0] Numerical Instability in Rates
- **Location**: [chem/rates.F90:42](file:///path/to/chem/rates.F90#L42)
- **Problem**: Missing molecular weight scaling factor in chemistry photolysis rate.
- **Rationale**: Atmospheric chemistry conservation requires scaling.
- **1-Click Suggestion**:
```suggestion
rate = 1.0_rk * temp * mw_scale
```

### [P2] Ponytail Dead Code: Remove Wrapper
- **Location**: [chem/utils.F90:15](file:///path/to/chem/utils.F90#L15)
- **Problem**: Dead wrapper function.
- **Rationale**: YAGNI simplification.
""",
        encoding="utf-8",
    )

    res = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 123,
            "review_file_path": str(md_path),
            "diff_text": """diff --git a/chem/rates.F90 b/chem/rates.F90
--- a/chem/rates.F90
+++ b/chem/rates.F90
@@ -40,5 +40,5 @@
 rate = 1.0 * temp
diff --git a/chem/utils.F90 b/chem/utils.F90
--- a/chem/utils.F90
+++ b/chem/utils.F90
@@ -10,10 +10,10 @@
 end subroutine
 """,
        },
    )
    data = json.loads(_tool_text(res))
    assert data["total_received"] == 2
    assert data["inserted_count"] == 2
    assert data["recorded_comments"][0]["priority_label"] == "Blocker"
    assert data["recorded_comments"][1]["priority_label"] == "Moderate"
    assert data["review_payload_path"] == str(
        (tmp_path / "review_payload.json").resolve()
    )
    payload_json = json.loads(
        (tmp_path / "review_payload.json").read_text(encoding="utf-8")
    )
    assert "event" not in payload_json
    assert len(payload_json["comments"]) == 2
    assert data["review_payload_path"] == str(
        (tmp_path / "review_payload.json").resolve()
    )
    payload_json = json.loads(
        (tmp_path / "review_payload.json").read_text(encoding="utf-8")
    )
    assert "event" not in payload_json
    assert len(payload_json["comments"]) == 2

    # Search FTS5
    search_res = await mcp_app.call_tool(
        "search_review_history",
        {"query": "photolysis", "repo": "ufs-community/CATChem"},
    )
    search_data = json.loads(_tool_text(search_res))
    assert len(search_data) == 1
    assert search_data[0]["line"] == 42


@pytest.mark.asyncio
async def test_record_review_comments_filters_out_of_diff_hunks(
    mcp_app: FastMCP, tmp_path: Path
) -> None:
    md_path = tmp_path / "review-diff-filter.md"
    md_path.write_text(
        """# Pull Request Review: [ufs-community/CATChem#999]

## 5. Detailed Findings & Machine-Applicable Suggestions

### [P1] In-Hunk Finding
- **Location**: `src/core.cpp:15`
- **Recommended Post Location**: Inline on `src/core.cpp` (line `15`)
- **Tag**: `[correctness]`

**Correctness: In-hunk issue**

Testing in-hunk.

**Suggested fix:** fix.

**Test:** test.

### [P2] Out-of-Hunk Finding
- **Location**: `src/core.cpp:250`
- **Recommended Post Location**: Inline on `src/core.cpp` (line `250`)
- **Tag**: `[robustness]`

**Robustness: Out-of-hunk issue**

Testing out-of-hunk.

**Suggested fix:** fix.

**Test:** test.
""",
        encoding="utf-8",
    )

    diff_text = """diff --git a/src/core.cpp b/src/core.cpp
--- a/src/core.cpp
+++ b/src/core.cpp
@@ -10,10 +10,10 @@
 void run() {
+    int x = 1;
 }
"""

    res = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 999,
            "review_file_path": str(md_path),
            "diff_text": diff_text,
        },
    )
    data = json.loads(_tool_text(res))
    assert data["total_received"] == 2
    payload_json = json.loads(
        (tmp_path / "review_payload.json").read_text(encoding="utf-8")
    )
    # Only the in-hunk finding is kept as an inline comment
    assert len(payload_json["comments"]) == 1
    assert payload_json["comments"][0]["line"] == 15
    # The top-level body is written to review_payload_body.md for copy-paste submission
    assert "body" not in payload_json
    body_path = tmp_path / "review_payload_body.md"
    assert data["review_body_path"] == str(body_path.resolve())
    body_md = body_path.read_text(encoding="utf-8")
    assert "### File-Level & Out-of-Diff Findings" in body_md
    assert "<details>" in body_md
    assert (
        "<summary><b>[P2 - Moderate] Out-of-Hunk Finding</b> (<code>src/core.cpp:250</code>)</summary>"
        in body_md
    )
    assert "</details>" in body_md
    assert "`src/core.cpp:250`" in body_md


@pytest.mark.asyncio
async def test_record_review_comments_with_raw_markdown_text(
    mcp_app: FastMCP,
) -> None:
    raw_text = """### [P1] Missing Allocation Status Check
- **Location**: [chem/driver.F90:110](file:///path/to/chem/driver.F90#L110)
- **Problem**: Memory allocation without stat=rc.
- **Rationale**: NOAA OMD standards require allocate checks.
"""
    res = await mcp_app.call_tool(
        "record_review_comments",
        {
            "pr_url": "https://github.com/ufs-community/CATChem/pull/456",
            "markdown_text": raw_text,
        },
    )
    data = json.loads(_tool_text(res))
    assert data["repo"] == "ufs-community/CATChem"
    assert data["pr_number"] == 456
    assert data["total_received"] == 1
    assert data["inserted_count"] == 1
    assert data["recorded_comments"][0]["priority_label"] == "Major"
    assert data["recorded_comments"][0]["criticality"] == 4


@pytest.mark.asyncio
async def test_record_review_comments_auto_fetches_diff(
    mcp_app: FastMCP, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from ufs_chem_pr_review_mcp.ingest.client import GitHubClient

    md_path = tmp_path / "review-auto-diff.md"
    md_path.write_text(
        """### [P1] Auto Diff Test
- **Location**: `src/core.cpp:12`
- **Problem**: Test problem.
""",
        encoding="utf-8",
    )

    sample_diff = """diff --git a/src/core.cpp b/src/core.cpp
--- a/src/core.cpp
+++ b/src/core.cpp
@@ -10,5 +10,5 @@
 int a = 1;
"""

    # 1. GitHubClient.get_pr_diff succeeds
    monkeypatch.setattr(GitHubClient, "get_pr_diff", lambda self, repo, pr: sample_diff)
    res1 = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 101,
            "review_file_path": str(md_path),
        },
    )
    data1 = json.loads(_tool_text(res1))
    assert data1["review_payload_path"] is not None

    # 2. GitHubClient.get_pr_diff fails, fallback to gh pr diff succeeds
    def raise_client_err(self: Any, repo: str, pr: int) -> str:
        raise RuntimeError("API error")

    monkeypatch.setattr(GitHubClient, "get_pr_diff", raise_client_err)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=["gh"], returncode=0, stdout=sample_diff, stderr=""
        ),
    )
    res2 = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 102,
            "review_file_path": str(md_path),
        },
    )
    data2 = json.loads(_tool_text(res2))
    assert data2["review_payload_path"] is not None

    # 3. Both GitHubClient.get_pr_diff and subprocess.run fail
    def raise_subproc_err(*a: Any, **kw: Any) -> Any:
        raise OSError("gh not found")

    monkeypatch.setattr(subprocess, "run", raise_subproc_err)
    res3 = await mcp_app.call_tool(
        "record_review_comments",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 103,
            "review_file_path": str(md_path),
        },
    )
    data3 = json.loads(_tool_text(res3))
    assert data3["review_payload_path"] is not None
