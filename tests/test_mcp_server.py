"""Unit tests for MCP server tools, resources, and prompts."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import respx
from mcp.server.fastmcp import FastMCP

from ufs_chem_pr_review_mcp.db.repository import ReviewDatabase
from ufs_chem_pr_review_mcp.server import create_mcp_server
from ufs_chem_pr_review_mcp.server import main as server_main


def _tool_text(res: Any) -> str:
    """Extract string text from FastMCP tool call result."""
    content_list, _ = res
    item = content_list[0]
    return getattr(item, "text", str(item))


def _res_text(res: Any) -> str:
    """Extract string content from FastMCP read_resource result."""
    items = list(res)
    item = items[0]
    return getattr(item, "content", str(item))


@pytest.fixture
def mcp_server_fixture(tmp_db_path: Path) -> FastMCP:
    db = ReviewDatabase(tmp_db_path)
    db.init_schema()
    db.upsert_repository(
        "ufs-community/CATChem", "https://github.com/ufs-community/CATChem", "develop"
    )
    return create_mcp_server(db_path=tmp_db_path)


@pytest.mark.asyncio
async def test_evaluate_diff_tool(mcp_server_fixture: FastMCP) -> None:
    diff_text = """diff --git a/chem/rates.F90 b/chem/rates.F90
--- a/chem/rates.F90
+++ b/chem/rates.F90
@@ -10,3 +10,4 @@
+  rate = 1.0 * temp
"""
    result = await mcp_server_fixture.call_tool(
        "evaluate_diff",
        {
            "diff_text": diff_text,
            "target_repo": "ufs-community/CATChem",
            "output_format": "markdown",
            "review_mode": "summary_and_inline",
            "include_ponytail_audit": True,
            "max_context_comments": 10,
        },
    )
    assert result is not None
    content_text = _tool_text(result)
    assert "rate = 1.0_rk" in content_text or "1.0_rk" in content_text
    assert "Critical Summary" in content_text or "findings" in content_text.lower()


@pytest.mark.asyncio
@respx.mock
async def test_evaluate_pr_tool(mcp_server_fixture: FastMCP) -> None:
    # Mock GitHub PR diff
    respx.get("https://api.github.com/repos/ufs-community/CATChem/pulls/12").respond(
        text="diff --git a/chem/rates.F90 b/chem/rates.F90\n--- a/chem/rates.F90\n+++ b/chem/rates.F90\n@@ -10,3 +10,4 @@\n+  rate = 1.0 * temp\n",
        headers={"content-type": "application/vnd.github.v3.diff"},
    )
    result = await mcp_server_fixture.call_tool(
        "evaluate_pr",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 12,
            "output_format": "github_json",
            "review_mode": "summary_and_inline",
            "include_ponytail_audit": True,
            "max_context_comments": 10,
        },
    )
    assert result is not None
    payload = json.loads(_tool_text(result))
    assert "comments" in payload
    assert payload["event"] in ["COMMENT", "REQUEST_CHANGES"]


@pytest.mark.asyncio
async def test_search_review_history_tool(mcp_server_fixture: FastMCP) -> None:
    result = await mcp_server_fixture.call_tool(
        "search_review_history",
        {
            "query": "molecular weight",
            "repo": "ufs-community/CATChem",
            "limit": 5,
        },
    )
    assert result is not None
    data = json.loads(_tool_text(result))
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_repo_review_stats_tool(mcp_server_fixture: FastMCP) -> None:
    result = await mcp_server_fixture.call_tool(
        "get_repo_review_stats",
        {"repo": "ufs-community/CATChem"},
    )
    assert result is not None
    stats = json.loads(_tool_text(result))
    assert stats["repo_name"] == "ufs-community/CATChem"
    assert "total_prs" in stats


@pytest.mark.asyncio
async def test_format_review_output_tool(mcp_server_fixture: FastMCP) -> None:
    findings = [
        {
            "path": "chem/rates.F90",
            "line": 11,
            "body": "Use double precision literal 1.0_rk",
            "category": "chemistry_physics",
            "criticality": 4,
            "suggested_change": "rate = 1.0_rk * temp",
        }
    ]
    # Test patch output
    patch_result = await mcp_server_fixture.call_tool(
        "format_review_output",
        {
            "findings": findings,
            "critical_summary": "All good except 1 precision nit.",
            "output_format": "patch",
        },
    )
    assert "diff --git" in _tool_text(patch_result) or "--- a/" in _tool_text(
        patch_result
    )

    # Test github_json output
    json_result = await mcp_server_fixture.call_tool(
        "format_review_output",
        {
            "findings": findings,
            "critical_summary": "Summary text",
            "output_format": "github_json",
        },
    )
    payload = json.loads(_tool_text(json_result))
    assert payload["body"] == "Summary text"
    assert len(payload["comments"]) == 1
    assert "```suggestion" in payload["comments"][0]["body"]


@pytest.mark.asyncio
async def test_generate_patch_tool(mcp_server_fixture: FastMCP) -> None:
    patches = [
        {
            "file_path": "chem/rates.F90",
            "start_line": 5,
            "end_line": 5,
            "original_code": "1.0",
            "replacement_code": "1.0_rk",
            "unified_hunk": "@@ -5,1 +5,1 @@\n-1.0\n+1.0_rk\n",
        }
    ]
    result = await mcp_server_fixture.call_tool(
        "generate_patch",
        {"patches": patches},
    )
    assert result is not None
    patch_data = json.loads(_tool_text(result))
    assert "--- a/chem/rates.F90" in patch_data["patch_text"]
    assert patch_data["total_additions"] == 1


@pytest.mark.asyncio
async def test_resources_and_prompts(mcp_server_fixture: FastMCP) -> None:
    # Test repositories resource
    repo_resource = await mcp_server_fixture.read_resource("ufs-chem://repositories")
    assert repo_resource is not None
    assert "ufs-community/CATChem" in _res_text(repo_resource)

    # Test guidelines list resource
    all_guidelines = await mcp_server_fixture.read_resource("ufs-chem://guidelines")
    assert all_guidelines is not None
    guidelines_list = json.loads(_res_text(all_guidelines))
    assert isinstance(guidelines_list, list)
    categories = [g["category"] for g in guidelines_list]
    assert "fortran" in categories
    assert "cpp" in categories
    assert "ee2" in categories

    # Test file-backed guidelines resources
    fortran_guide = await mcp_server_fixture.read_resource(
        "ufs-chem://guidelines/fortran"
    )
    assert "Flux" in _res_text(fortran_guide)

    cpp_guide = await mcp_server_fixture.read_resource("ufs-chem://guidelines/cpp")
    assert "Forge" in _res_text(cpp_guide)

    ee2_guide = await mcp_server_fixture.read_resource("ufs-chem://guidelines/ee2")
    assert "Environment Equivalence" in _res_text(ee2_guide)

    unknown_guide = await mcp_server_fixture.read_resource(
        "ufs-chem://guidelines/nonexistent"
    )
    assert "No specific guidelines registered" in _res_text(unknown_guide)

    # Test guidelines resource fallback dictionary
    guide_resource = await mcp_server_fixture.read_resource(
        "ufs-chem://guidelines/chemistry_physics"
    )
    assert guide_resource is not None
    assert "molecular weight" in _res_text(guide_resource).lower()

    # Test review_pr prompt
    prompt = await mcp_server_fixture.get_prompt(
        "review_pr",
        arguments={"repo": "ufs-community/CATChem", "pr_number": "42"},
    )
    assert prompt is not None
    msg_content = prompt.messages[0].content
    assert "evaluate_pr" in getattr(msg_content, "text", str(msg_content))
    assert "Flux Fortran" in getattr(msg_content, "text", str(msg_content))


@pytest.mark.asyncio
async def test_evaluate_diff_multi_file_and_ponytail(
    mcp_server_fixture: FastMCP,
) -> None:
    multi_diff = """diff --git a/chem/first.F90 b/chem/first.F90
--- a/chem/first.F90
+++ b/chem/first.F90
@@ -1,5 +1,6 @@
+  ! x = old_code(1, 2)
diff --git a/chem/second.F90 b/chem/second.F90
--- a/chem/second.F90
+++ b/chem/second.F90
@@ -10,3 +10,4 @@
+  rate = 1.0 * temp
"""
    # 1. output_format="patch"
    res_patch = await mcp_server_fixture.call_tool(
        "evaluate_diff",
        {
            "diff_text": multi_diff,
            "target_repo": "ufs-community/CATChem",
            "output_format": "patch",
        },
    )
    assert "diff --git" in _tool_text(res_patch)

    # 2. output_format="github_json"
    res_json = await mcp_server_fixture.call_tool(
        "evaluate_diff",
        {
            "diff_text": multi_diff,
            "target_repo": "ufs-community/CATChem",
            "output_format": "github_json",
        },
    )
    payload = json.loads(_tool_text(res_json))
    assert payload["event"] == "REQUEST_CHANGES"
    assert any(c["path"] == "chem/first.F90" for c in payload["comments"])

    # 3. output_format="markdown"
    res_md = await mcp_server_fixture.call_tool(
        "evaluate_diff",
        {
            "diff_text": multi_diff,
            "target_repo": "ufs-community/CATChem",
            "output_format": "markdown",
        },
    )
    assert "Net lines removable estimate" in _tool_text(res_md)
    assert "chem/first.F90" in _tool_text(res_md)


@pytest.mark.asyncio
async def test_evaluate_diff_clean_code(mcp_server_fixture: FastMCP) -> None:
    clean_diff = """diff --git a/chem/clean.F90 b/chem/clean.F90
--- a/chem/clean.F90
+++ b/chem/clean.F90
@@ -1,2 +1,3 @@
+  real(rk) :: rate = 1.0_rk
"""
    res = await mcp_server_fixture.call_tool(
        "evaluate_diff",
        {
            "diff_text": clean_diff,
            "target_repo": "ufs-community/CATChem",
            "output_format": "markdown",
        },
    )
    assert (
        "No critical issues or domain violations identified. Code looks clean."
        in _tool_text(res)
    )
    assert "Lean already. Ship." in _tool_text(res)


@pytest.mark.asyncio
@respx.mock
async def test_evaluate_pr_formats_and_error(mcp_server_fixture: FastMCP) -> None:
    # Test patch format
    respx.get("https://api.github.com/repos/ufs-community/CATChem/pulls/20").respond(
        text="diff --git a/chem/rates.F90 b/chem/rates.F90\n--- a/chem/rates.F90\n+++ b/chem/rates.F90\n@@ -1,2 +1,3 @@\n+  x = 1.0 * y\n",
        headers={"content-type": "application/vnd.github.v3.diff"},
    )
    res_patch = await mcp_server_fixture.call_tool(
        "evaluate_pr",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 20,
            "output_format": "patch",
        },
    )
    assert "diff --git" in _tool_text(res_patch)

    # Test markdown format
    res_md = await mcp_server_fixture.call_tool(
        "evaluate_pr",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 20,
            "output_format": "markdown",
        },
    )
    assert "Code Review Summary" in _tool_text(res_md)

    # Test error handling on GitHub failure
    respx.get("https://api.github.com/repos/ufs-community/CATChem/pulls/999").respond(
        status_code=500,
        text="Internal Server Error",
    )
    respx.get(
        "https://api.github.com/repos/ufs-community/CATChem/pulls/999/files"
    ).respond(
        status_code=500,
        text="Internal Server Error",
    )
    res_err = await mcp_server_fixture.call_tool(
        "evaluate_pr",
        {
            "repo": "ufs-community/CATChem",
            "pr_number": 999,
        },
    )
    err_data = json.loads(_tool_text(res_err))
    assert "error" in err_data
    assert "Failed to fetch PR diff from GitHub" in err_data["message"]


@pytest.mark.asyncio
async def test_format_review_output_markdown(mcp_server_fixture: FastMCP) -> None:
    findings = [
        {
            "path": "chem/rates.F90",
            "line": 15,
            "body": "Precision nit",
            "suggested_change": "rate = 1.0_rk",
        }
    ]
    res = await mcp_server_fixture.call_tool(
        "format_review_output",
        {
            "findings": findings,
            "critical_summary": "Summary details",
            "output_format": "markdown",
        },
    )
    text = _tool_text(res)
    assert "## Code Review Summary" in text
    assert "```suggestion\n  rate = 1.0_rk\n  ```" in text


def test_server_main_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_mcp = MagicMock()
    monkeypatch.setattr(
        "ufs_chem_pr_review_mcp.server.create_mcp_server", lambda: mock_mcp
    )
    server_main()
    mock_mcp.run.assert_called_once_with(transport="stdio")
