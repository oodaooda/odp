"""GitHub integration: PR creation and status checks.

Config-gated via ODP_GITHUB_TOKEN env var. When not set, all operations
are no-ops and return None.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PRResult:
    """Result from creating a GitHub PR."""
    url: str
    number: int
    html_url: str


async def create_pr(
    *,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
    token: str | None = None,
) -> PRResult | None:
    """Create a GitHub pull request.

    Args:
        repo: "owner/repo" format
        title: PR title
        body: PR body (markdown)
        head: source branch
        base: target branch
        token: GitHub token (falls back to ODP_GITHUB_TOKEN env)
    """
    token = token or os.getenv("ODP_GITHUB_TOKEN", "")
    if not token:
        logger.info("ODP_GITHUB_TOKEN not set; skipping PR creation")
        return None

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed; cannot create PR")
        return None

    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"title": title, "body": body, "head": head, "base": base}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=data, headers=headers, timeout=30)
        resp.raise_for_status()
        pr = resp.json()
        return PRResult(
            url=pr["url"],
            number=pr["number"],
            html_url=pr["html_url"],
        )


async def post_status(
    *,
    repo: str,
    sha: str,
    state: str,
    context: str,
    description: str = "",
    target_url: str = "",
    token: str | None = None,
) -> bool:
    """Post a commit status to GitHub.

    Args:
        repo: "owner/repo" format
        sha: commit SHA
        state: "success", "failure", "pending", "error"
        context: status context (e.g., "odp/engineer")
        description: short description
        target_url: URL linking back to ODP
        token: GitHub token
    """
    token = token or os.getenv("ODP_GITHUB_TOKEN", "")
    if not token:
        return False

    try:
        import httpx
    except ImportError:
        return False

    url = f"https://api.github.com/repos/{repo}/statuses/{sha}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data: dict[str, Any] = {"state": state, "context": context}
    if description:
        data["description"] = description[:140]
    if target_url:
        data["target_url"] = target_url

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=data, headers=headers, timeout=30)
        return resp.status_code < 300
