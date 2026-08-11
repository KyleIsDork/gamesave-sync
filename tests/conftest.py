"""Shared fixtures.

Tests never touch the network or the developer's real config: the GitHub client
is replaced by an in-memory fake, and config/data directories are redirected
into tmp_path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Qt needs a platform plugin; CI runners have no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gamesync.github import CommitInfo, TreeEntry, git_blob_sha  # noqa: E402
from gamesync.models import AppConfig, GameProfile, Source  # noqa: E402


class FakeGitHub:
    """In-memory content-addressed store mimicking the git data API.

    Trees are stored flattened (path -> blob sha), which is enough for the
    engine: it only ever reads recursive trees and writes with a base_tree.
    """

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, dict] = {}
        self.refs: dict[str, str] = {}
        self.counter = 0
        self.blob_uploads = 0

        empty_tree = self._put_tree({})
        self.refs["main"] = self._put_commit("initial commit", empty_tree, [])

    # -- internals
    def _next(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter:039d}"

    def _put_tree(self, mapping: dict[str, str]) -> str:
        sha = self._next("t")
        self.trees[sha] = dict(mapping)
        return sha

    def _put_commit(self, message: str, tree: str, parents: list[str]) -> str:
        sha = self._next("c")
        self.commits[sha] = {
            "message": message,
            "tree": {"sha": tree},
            "parents": parents,
        }
        return sha

    def head_tree(self, branch: str = "main") -> dict[str, str]:
        return self.trees[self.commits[self.refs[branch]]["tree"]["sha"]]

    # -- API surface used by SyncEngine
    def get_branch_head(self, owner, repo, branch):
        return self.refs.get(branch)

    def get_commit(self, owner, repo, sha):
        return self.commits[sha]

    def get_tree(self, owner, repo, sha, recursive=True):
        entries = [
            TreeEntry(path=p, mode="100644", type="blob", sha=s, size=len(self.blobs[s]))
            for p, s in sorted(self.trees[sha].items())
        ]
        return entries, False

    def create_blob(self, owner, repo, content):
        self.blob_uploads += 1
        sha = git_blob_sha(content)
        self.blobs[sha] = content
        return sha

    def get_blob(self, owner, repo, sha):
        return self.blobs[sha]

    def create_tree(self, owner, repo, entries, base_tree=None):
        mapping = dict(self.trees[base_tree]) if base_tree else {}
        for entry in entries:
            if entry["sha"] is None:
                mapping.pop(entry["path"], None)
            else:
                mapping[entry["path"]] = entry["sha"]
        return self._put_tree(mapping)

    def create_commit(self, owner, repo, message, tree, parents):
        return self._put_commit(message, tree, parents)

    def update_ref(self, owner, repo, branch, sha, force=False):
        self.refs[branch] = sha

    def list_commits(self, owner, repo, path=None, branch=None, limit=50):
        out: list[CommitInfo] = []
        sha = self.refs.get(branch or "main")
        while sha:
            commit = self.commits[sha]
            if path is None or any(
                p.startswith(path) for p in self.trees[commit["tree"]["sha"]]
            ):
                out.append(
                    CommitInfo(
                        sha=sha,
                        message=commit["message"],
                        date="2026-08-11T12:00:00Z",
                        author="tester",
                    )
                )
            parents = commit["parents"]
            sha = parents[0] if parents else None
        return out[:limit]

    def ensure_repo(self, owner, name):
        return {"full_name": f"{owner}/{name}", "default_branch": "main"}, False


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(repo_owner="tester", repo_name="game-saves", branch="main")


@pytest.fixture
def save_dir(tmp_path: Path) -> Path:
    """A game save folder with a couple of files and some noise to exclude."""
    saves = tmp_path / "MyGame" / "Saves"
    saves.mkdir(parents=True)
    (saves / "slot1.dat").write_bytes(b"first save")
    (saves / "slot2.dat").write_bytes(b"second save")
    (saves / "debug.log").write_text("noise that should be excluded")
    (saves / "nested").mkdir()
    (saves / "nested" / "meta.json").write_text('{"a":1}')
    return saves


@pytest.fixture
def profile(save_dir: Path) -> GameProfile:
    return GameProfile(
        name="My Game", sources=[Source(path=str(save_dir), kind="dir")]
    )


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Redirect the app's config/data dirs so tests never touch the real ones."""
    import gamesync.paths as paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    data_dir.mkdir()

    monkeypatch.setattr(paths, "config_dir", lambda: config_dir)
    monkeypatch.setattr(paths, "data_dir", lambda: data_dir)
    monkeypatch.setattr(
        paths, "safety_dir", lambda: (data_dir / "pre-restore").resolve()
    )
    (data_dir / "pre-restore").mkdir()
    return config_dir, data_dir
