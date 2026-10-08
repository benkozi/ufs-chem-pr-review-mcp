"""GitHub REST API client for fetching PRs, diffs, comments, and commits."""

from typing import Any

import httpx

from ufs_chem_pr_review_mcp.logs import get_logger

logger = get_logger("ingest.client")


class GitHubApiError(Exception):
    """Exception raised when a GitHub API request fails or is rate-limited."""


class GitHubClient:
    """Async/Sync HTTP client for GitHub REST API interactions."""

    def __init__(
        self, token: str | None = None, base_url: str = "https://api.github.com"
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ufs-chem-pr-review-mcp",
        }
        if token:
            headers["Authorization"] = f"token {token}"
        self._client = httpx.Client(headers=headers, timeout=30.0)

    def _check_response(self, response: httpx.Response) -> None:
        """Raise typed GitHubApiError on HTTP error status codes."""
        if response.status_code == 403:
            msg = response.text
            if "rate limit" in msg.lower():
                raise GitHubApiError(
                    "GitHub API rate limit exceeded. Set UFS_CHEM_GITHUB_TOKEN to increase limits."
                )
            raise GitHubApiError(f"GitHub API Forbidden (403): {msg}")
        if response.is_error:
            raise GitHubApiError(
                f"GitHub API error {response.status_code}: {response.text}"
            )

    def get_pull_requests(self, repo: str, state: str = "all") -> list[dict[str, Any]]:
        """Fetch pull requests for a repository."""
        url = f"{self.base_url}/repos/{repo}/pulls"
        resp = self._client.get(url, params={"state": state, "per_page": 50})
        self._check_response(resp)
        return list(resp.json())

    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Fetch unified diff for a pull request, falling back to paginated file diffs if too large."""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        diff_resp = self._client.get(
            url, headers={"Accept": "application/vnd.github.v3.diff"}
        )

        if diff_resp.status_code == 200 and "diff --git" in diff_resp.text:
            return diff_resp.text

        logger.warning(
            f"Unified diff for {repo}#{pr_number} unavailable (status {diff_resp.status_code}); falling back to file diffs."
        )
        # Fallback to paginated /pulls/{pr}/files
        files_url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/files"
        files_resp = self._client.get(files_url, params={"per_page": 100})
        self._check_response(files_resp)

        hunks: list[str] = []
        for file_info in files_resp.json():
            filename = file_info.get("filename", "")
            patch = file_info.get("patch", "")
            if patch:
                hunks.append(
                    f"diff --git a/{filename} b/{filename}\n--- a/{filename}\n+++ b/{filename}\n{patch}"
                )

        return "\n".join(hunks)

    def get_pr_comments(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Fetch review comments for a pull request."""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/comments"
        resp = self._client.get(url, params={"per_page": 100})
        self._check_response(resp)
        return list(resp.json())

    def get_pr_commits(self, repo: str, pr_number: int) -> list[dict[str, Any]]:
        """Fetch commit list for a pull request."""
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/commits"
        resp = self._client.get(url, params={"per_page": 100})
        self._check_response(resp)
        return list(resp.json())

    def get_commit_detail(self, repo: str, commit_sha: str) -> dict[str, Any]:
        """Fetch individual commit details including file patches."""
        url = f"{self.base_url}/repos/{repo}/commits/{commit_sha}"
        resp = self._client.get(url)
        self._check_response(resp)
        return dict(resp.json())

    def close(self) -> None:
        """Close the underlying HTTP client session."""
        self._client.close()
