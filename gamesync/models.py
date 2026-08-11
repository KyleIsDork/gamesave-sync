from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from .util import slugify

# Never worth syncing, and .git in particular would confuse the repo.
DEFAULT_EXCLUDES = [
    ".git",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.tmp",
    "*.log",
    "*.bak~",
]


def current_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


@dataclass
class Source:
    """One file or folder belonging to a game, stored as a tokenized path.

    ``kind`` is recorded when the source is added rather than probed later: a
    profile synced from another machine may point at a path that does not exist
    here yet, and restore still needs to know whether it names a file or a
    directory.
    """

    path: str
    kind: str = "dir"  # "dir" | "file"
    label: str = ""
    excludes: list[str] = field(default_factory=list)

    @property
    def is_file(self) -> bool:
        return self.kind == "file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "label": self.label,
            "excludes": list(self.excludes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        kind = str(data.get("kind", "dir"))
        return cls(
            path=str(data.get("path", "")),
            kind=kind if kind in ("dir", "file") else "dir",
            label=str(data.get("label", "")),
            excludes=[str(x) for x in data.get("excludes", [])],
        )


@dataclass
class GameProfile:
    name: str
    slug: str = ""
    sources: list[Source] = field(default_factory=list)
    interval_minutes: int = 30
    enabled: bool = True
    excludes: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))

    # Local bookkeeping; not authoritative, the repo history is.
    last_backup_at: str | None = None
    last_commit_sha: str | None = None
    last_status: str = ""
    last_error: str = ""

    # path-sets seen on other machines, keyed by platform, so a profile pulled
    # down on a new OS can suggest where the saves probably live.
    platform_paths: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slugify(self.name)

    @property
    def repo_dir(self) -> str:
        return f"games/{self.slug}"

    @property
    def data_prefix(self) -> str:
        return f"games/{self.slug}/data/"

    @property
    def profile_path(self) -> str:
        return f"games/{self.slug}/profile.json"

    def effective_excludes(self, source: Source) -> list[str]:
        return list(self.excludes) + list(source.excludes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "sources": [s.to_dict() for s in self.sources],
            "interval_minutes": self.interval_minutes,
            "enabled": self.enabled,
            "excludes": list(self.excludes),
            "last_backup_at": self.last_backup_at,
            "last_commit_sha": self.last_commit_sha,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "platform_paths": {k: list(v) for k, v in self.platform_paths.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameProfile":
        profile = cls(
            name=str(data.get("name", "Untitled")),
            slug=str(data.get("slug", "")),
            sources=[Source.from_dict(s) for s in data.get("sources", [])],
            interval_minutes=int(data.get("interval_minutes", 30)),
            enabled=bool(data.get("enabled", True)),
            excludes=[str(x) for x in data.get("excludes", DEFAULT_EXCLUDES)],
            last_backup_at=data.get("last_backup_at"),
            last_commit_sha=data.get("last_commit_sha"),
            last_status=str(data.get("last_status", "")),
            last_error=str(data.get("last_error", "")),
            platform_paths={
                str(k): [str(p) for p in v]
                for k, v in (data.get("platform_paths") or {}).items()
            },
        )
        return profile

    def to_repo_dict(self) -> dict[str, Any]:
        """The profile.json committed alongside the saves, so the repo is self-describing."""
        platform_paths = {k: list(v) for k, v in self.platform_paths.items()}
        platform_paths[current_platform()] = [s.path for s in self.sources]
        return {
            "schema": 1,
            "name": self.name,
            "slug": self.slug,
            "interval_minutes": self.interval_minutes,
            "excludes": list(self.excludes),
            "sources": [s.to_dict() for s in self.sources],
            "platform_paths": platform_paths,
        }


@dataclass
class AppConfig:
    repo_name: str = "game-saves"
    repo_owner: str = ""
    branch: str = "main"
    theme: str = "dark"
    auto_backup: bool = True
    default_interval_minutes: int = 30
    backup_on_launch: bool = False
    games: list[GameProfile] = field(default_factory=list)

    def game_by_slug(self, slug: str) -> GameProfile | None:
        return next((g for g in self.games if g.slug == slug), None)

    def unique_slug(self, name: str, exclude: str | None = None) -> str:
        base = slugify(name)
        taken = {g.slug for g in self.games if g.slug != exclude}
        if base not in taken:
            return base
        i = 2
        while f"{base}-{i}" in taken:
            i += 1
        return f"{base}-{i}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "repo_name": self.repo_name,
            "repo_owner": self.repo_owner,
            "branch": self.branch,
            "theme": self.theme,
            "auto_backup": self.auto_backup,
            "default_interval_minutes": self.default_interval_minutes,
            "backup_on_launch": self.backup_on_launch,
            "games": [g.to_dict() for g in self.games],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            repo_name=str(data.get("repo_name", "game-saves")),
            repo_owner=str(data.get("repo_owner", "")),
            branch=str(data.get("branch", "main")),
            theme=str(data.get("theme", "dark")),
            auto_backup=bool(data.get("auto_backup", True)),
            default_interval_minutes=int(data.get("default_interval_minutes", 30)),
            backup_on_launch=bool(data.get("backup_on_launch", False)),
            games=[GameProfile.from_dict(g) for g in data.get("games", [])],
        )
