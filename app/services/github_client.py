"""GitHub client — recent activity for the authenticated user.

Auth: Personal Access Token read fresh from GITHUB_PAT_FILE on each request
(same rotation-friendly pattern as the Asana PAT). A classic PAT with no
scopes sees public activity; add `repo` to include private repos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config import config

log = logging.getLogger("mnemosyne.github")

API = "https://api.github.com"
TIMEOUT_SECONDS = 15.0


class GitHubError(RuntimeError):
    pass


class GitHubNotConfigured(GitHubError):
    pass


@dataclass
class Activity:
    summary: str       # "pushed 3 commits to main"
    repo: str          # "owner/name"
    url: str           # where clicking should land
    at: datetime       # tz-aware UTC


def _headers() -> dict[str, str]:
    token = config.github_pat
    if not token:
        raise GitHubNotConfigured(
            f"GitHub PAT not configured (looked at {config.github_pat_file})"
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _get(path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=_headers()) as client:
        resp = await client.get(f"{API}{path}", **kwargs)
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub GET {path} → {resp.status_code}: {resp.text[:300]}")
    return resp


async def login() -> str:
    resp = await _get("/user")
    return resp.json().get("login", "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _describe(event: dict) -> tuple[str, str] | None:
    """(summary, url) for event types worth glancing at; None to skip."""
    etype = event.get("type", "")
    payload = event.get("payload") or {}
    repo = (event.get("repo") or {}).get("name", "")
    repo_url = f"https://github.com/{repo}"

    if etype == "PushEvent":
        branch = (payload.get("ref") or "").removeprefix("refs/heads/")
        n = payload.get("size") or len(payload.get("commits") or [])
        url = f"{repo_url}/commits/{branch}" if branch else repo_url
        return f"pushed {_plural(n, 'commit')} to {branch or '?'}", url

    if etype == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        action = payload.get("action", "")
        if action == "closed" and pr.get("merged"):
            action = "merged"
        if action not in ("opened", "merged", "closed", "reopened"):
            return None
        title = pr.get("title", "")
        return f"{action} PR #{pr.get('number', '?')}: {title}", pr.get("html_url", repo_url)

    if etype == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        return f"reviewed PR #{pr.get('number', '?')}: {pr.get('title', '')}", pr.get("html_url", repo_url)

    if etype == "IssuesEvent":
        action = payload.get("action", "")
        if action not in ("opened", "closed", "reopened"):
            return None
        issue = payload.get("issue") or {}
        return f"{action} issue #{issue.get('number', '?')}: {issue.get('title', '')}", issue.get("html_url", repo_url)

    if etype == "IssueCommentEvent":
        if payload.get("action") != "created":
            return None
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        return f"commented on #{issue.get('number', '?')}: {issue.get('title', '')}", comment.get("html_url", repo_url)

    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "")
        if ref_type == "repository":
            return "created repository", repo_url
        if ref_type == "tag":
            return f"tagged {payload.get('ref', '')}", repo_url
        return None  # branch creations are noise

    if etype == "ReleaseEvent":
        if payload.get("action") != "published":
            return None
        release = payload.get("release") or {}
        return f"released {release.get('tag_name', '')}", release.get("html_url", repo_url)

    return None


async def recent_activity(limit: int = 12) -> list[Activity]:
    user = await login()
    resp = await _get(f"/users/{user}/events", params={"per_page": 50})
    out: list[Activity] = []
    for event in resp.json():
        described = _describe(event)
        if described is None:
            continue
        summary, url = described
        created = event.get("created_at", "")
        try:
            at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            at = datetime.now(timezone.utc)
        out.append(
            Activity(
                summary=summary,
                repo=(event.get("repo") or {}).get("name", ""),
                url=url,
                at=at,
            )
        )
        if len(out) >= limit:
            break
    return out
