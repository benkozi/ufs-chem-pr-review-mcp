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
        },
    )
    data = json.loads(_tool_text(res))
    assert data["total_received"] == 2
    assert data["inserted_count"] == 2
    assert data["recorded_comments"][0]["priority_label"] == "Blocker"
    assert data["recorded_comments"][1]["priority_label"] == "Moderate"

    # Search FTS5
    search_res = await mcp_app.call_tool(
        "search_review_history",
        {"query": "photolysis", "repo": "ufs-community/CATChem"},
    )
    search_data = json.loads(_tool_text(search_res))
    assert len(search_data) == 1
    assert search_data[0]["line"] == 42


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
