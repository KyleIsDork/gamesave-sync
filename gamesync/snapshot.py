"""Reading a game's save files off disk into an in-memory snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .github import git_blob_sha
from .models import GameProfile, Source
from .paths import expand
from .util import matches_any, slugify

# A single save file this large is almost certainly not a save file.
MAX_FILE_BYTES = 50 * 1024 * 1024
# Past this, the GitHub API gets slow and the repo gets unpleasant.
WARN_TOTAL_BYTES = 100 * 1024 * 1024


@dataclass
class FileEntry:
    repo_path: str  # relative to the game dir, e.g. "data/profile/save1.dat"
    abs_path: Path
    data: bytes
    sha: str

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class Snapshot:
    files: list[FileEntry]
    warnings: list[str]
    missing_sources: list[str]

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def is_empty(self) -> bool:
        return not self.files


def source_label(source: Source, used: set[str]) -> str:
    """Folder name for this source inside the repo, unique within the game."""
    if source.label:
        base = slugify(source.label, fallback="source")
    else:
        expanded = expand(source.path)
        base = slugify(expanded.name or expanded.parent.name, fallback="source")

    label = base
    i = 2
    while label in used:
        label = f"{base}-{i}"
        i += 1
    used.add(label)
    return label


def collect(profile: GameProfile) -> Snapshot:
    files: list[FileEntry] = []
    warnings: list[str] = []
    missing: list[str] = []
    used_labels: set[str] = set()
    seen_paths: set[str] = set()

    for source in profile.sources:
        root = expand(source.path)
        label = source_label(source, used_labels)
        excludes = profile.effective_excludes(source)

        if not root.exists():
            missing.append(source.path)
            continue

        if source.is_file or root.is_file():
            candidates = [(root, root.name)]
        else:
            candidates = []
            for path in sorted(root.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if matches_any(rel, excludes):
                    continue
                candidates.append((path, rel))

        for abs_path, rel in candidates:
            try:
                size = abs_path.stat().st_size
            except OSError as exc:
                warnings.append(f"Could not stat {abs_path.name}: {exc}")
                continue

            if size > MAX_FILE_BYTES:
                warnings.append(
                    f"Skipped {rel} — {size // (1024 * 1024)} MB is over the "
                    f"{MAX_FILE_BYTES // (1024 * 1024)} MB per-file limit."
                )
                continue

            try:
                data = abs_path.read_bytes()
            except OSError as exc:
                # Locked by the running game is the common case here.
                warnings.append(f"Could not read {rel}: {exc}")
                continue

            repo_path = f"data/{label}/{rel}"
            if repo_path in seen_paths:
                continue
            seen_paths.add(repo_path)
            files.append(
                FileEntry(
                    repo_path=repo_path,
                    abs_path=abs_path,
                    data=data,
                    sha=git_blob_sha(data),
                )
            )

    snapshot = Snapshot(files=files, warnings=warnings, missing_sources=missing)
    if snapshot.total_bytes > WARN_TOTAL_BYTES:
        warnings.append(
            f"This game's saves total {snapshot.total_bytes // (1024 * 1024)} MB. "
            "Large repos sync slowly — consider excluding screenshots or video."
        )
    return snapshot


def resolve_restore_target(
    profile: GameProfile, repo_path: str
) -> tuple[Path | None, str]:
    """Map ``data/<label>/<rel>`` back to an absolute path on this machine.

    Returns (path, reason-if-unresolvable).
    """
    if not repo_path.startswith("data/"):
        return None, "not a save file"

    remainder = repo_path[len("data/") :]
    label, _, rel = remainder.partition("/")
    if not label or not rel:
        return None, "malformed path"

    # Repo contents decide where bytes get written, so refuse anything that
    # could climb out of the source root.
    parts = rel.split("/")
    if any(p in ("..", "") for p in parts) or Path(rel).is_absolute():
        return None, "unsafe path"

    used: set[str] = set()
    for source in profile.sources:
        if source_label(source, used) != label:
            continue
        root = expand(source.path)
        if source.is_file:
            # Single-file source: repo path is data/<label>/<filename>.
            return root, ""
        target = root / rel
        try:
            target.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError:
            return None, "unsafe path"
        return target, ""

    return None, f"no source on this machine matches '{label}'"
