"""Minimal GitHub REST client covering repo creation and the git data API.

Deliberately no local clone and no ``git`` binary: save files are small, and
committing through the trees API keeps the tool to a pure-Python dependency set
that behaves identically on every OS.
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from . import APP_SLUG, VERSION

API_ROOT = "https://api.github.com"
TOKEN_SCOPE_URL = (
    "https://github.com/settings/tokens/new"
    "?scopes=repo&description=GameSave%20Sync"
)


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AuthError(GitHubError):
    pass


def git_blob_sha(data: bytes) -> str:
    """The SHA-1 git itself would give this content.

    Computing it locally means we can diff against the remote tree and skip
    uploading anything unchanged, usually that makes a backup zero uploads.
    """
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


@dataclass
class TreeEntry:
    path: str
    mode: str
    type: str
    sha: str | None
    size: int = 0


@dataclass
class CommitInfo:
    sha: str
    message: str
    date: str
    author: str


class GitHubClient:
    def __init__(self, token: str, timeout: float = 30.0) -> None:
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"{APP_SLUG}/{VERSION}",
            }
        )

    # ---- plumbing -------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        expect: Iterable[int] = (200, 201),
        retries: int = 3,
    ) -> Any:
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                response = self.session.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = GitHubError(f"Network error talking to GitHub: {exc}")
                time.sleep(1.5 * (attempt + 1))
                continue

            if response.status_code in expect:
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()

            if response.status_code == 401:
                raise AuthError(
                    "GitHub rejected the token. It may be expired or revoked.", 401
                )

            # Secondary rate limit / abuse detection asks us to back off.
            if response.status_code in (403, 429):
                retry_after = response.headers.get("Retry-After")
                remaining = response.headers.get("X-RateLimit-Remaining")
                if retry_after or remaining == "0":
                    delay = float(retry_after) if retry_after else 60.0
                    if attempt < retries - 1:
                        time.sleep(min(delay, 90.0))
                        continue
                    raise GitHubError(
                        "GitHub rate limit reached. Try again in a few minutes.",
                        response.status_code,
                    )
                raise GitHubError(
                    self._error_message(response, "Permission denied by GitHub."),
                    403,
                )

            if 500 <= response.status_code < 600 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue

            raise GitHubError(
                self._error_message(response, f"GitHub returned {response.status_code}"),
                response.status_code,
            )

        raise last_error or GitHubError("GitHub request failed.")

    @staticmethod
    def _error_message(response: requests.Response, fallback: str) -> str:
        try:
            payload = response.json()
        except ValueError:
            return fallback
        message = payload.get("message") or fallback
        errors = payload.get("errors") or []
        details = "; ".join(
            e.get("message") or f"{e.get('field', '')} {e.get('code', '')}".strip()
            for e in errors
            if isinstance(e, dict)
        )
        return f"{message} ({details})" if details else message

    # ---- account & repo -------------------------------------------------

    def whoami(self) -> dict[str, Any]:
        return self._request("GET", "/user")

    def get_repo(self, owner: str, repo: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/repos/{owner}/{repo}")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise

    def create_repo(self, name: str, description: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            "/user/repos",
            json_body={
                "name": name,
                "description": description or "Game save backups (managed by GameSave Sync)",
                "private": True,
                "auto_init": True,
                "has_issues": False,
                "has_wiki": False,
                "has_projects": False,
            },
        )

    def ensure_repo(self, owner: str, name: str) -> tuple[dict[str, Any], bool]:
        """Returns (repo, created)."""
        existing = self.get_repo(owner, name)
        if existing:
            return existing, False
        return self.create_repo(name), True

    # ---- git data API ---------------------------------------------------

    def get_branch_head(self, owner: str, repo: str, branch: str) -> str | None:
        try:
            ref = self._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise
        return ref["object"]["sha"]

    def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        return self._request("GET", f"/repos/{owner}/{repo}/git/commits/{sha}")

    def get_tree(
        self, owner: str, repo: str, sha: str, recursive: bool = True
    ) -> tuple[list[TreeEntry], bool]:
        params = {"recursive": "1"} if recursive else None
        data = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{sha}", params=params)
        entries = [
            TreeEntry(
                path=e["path"],
                mode=e["mode"],
                type=e["type"],
                sha=e.get("sha"),
                size=int(e.get("size") or 0),
            )
            for e in data.get("tree", [])
        ]
        return entries, bool(data.get("truncated"))

    def create_blob(self, owner: str, repo: str, content: bytes) -> str:
        payload = {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        }
        data = self._request("POST", f"/repos/{owner}/{repo}/git/blobs", json_body=payload)
        return data["sha"]

    def get_blob(self, owner: str, repo: str, sha: str) -> bytes:
        data = self._request("GET", f"/repos/{owner}/{repo}/git/blobs/{sha}")
        encoding = data.get("encoding")
        if encoding == "base64":
            return base64.b64decode(data["content"])
        return str(data.get("content", "")).encode("utf-8")

    def create_tree(
        self,
        owner: str,
        repo: str,
        entries: list[dict[str, Any]],
        base_tree: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"tree": entries}
        if base_tree:
            payload["base_tree"] = base_tree
        data = self._request("POST", f"/repos/{owner}/{repo}/git/trees", json_body=payload)
        return data["sha"]

    def create_commit(
        self,
        owner: str,
        repo: str,
        message: str,
        tree: str,
        parents: list[str],
    ) -> str:
        data = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json_body={"message": message, "tree": tree, "parents": parents},
        )
        return data["sha"]

    def update_ref(
        self, owner: str, repo: str, branch: str, sha: str, force: bool = False
    ) -> None:
        self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json_body={"sha": sha, "force": force},
        )

    def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        path: str | None = None,
        branch: str | None = None,
        limit: int = 50,
    ) -> list[CommitInfo]:
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if path:
            params["path"] = path
        if branch:
            params["sha"] = branch
        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/commits", params=params)
        except GitHubError as exc:
            # An empty repo (or a branch with no commits touching path) 409s.
            if exc.status in (409, 404):
                return []
            raise

        commits = []
        for item in data or []:
            commit = item.get("commit", {})
            author = commit.get("author", {}) or {}
            commits.append(
                CommitInfo(
                    sha=item["sha"],
                    message=(commit.get("message") or "").strip(),
                    date=author.get("date", ""),
                    author=author.get("name", ""),
                )
            )
        return commits
