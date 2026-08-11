"""Backup and restore orchestration against the GitHub git data API."""

from __future__ import annotations

import json
import platform
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import APP_NAME
from .github import CommitInfo, GitHubClient, GitHubError, TreeEntry, git_blob_sha
from .models import AppConfig, GameProfile
from .paths import safety_dir
from .snapshot import Snapshot, collect, resolve_restore_target
from .util import humanize_bytes, iso_now, utc_now

Progress = Callable[[int, str], None]

FILE_MODE = "100644"

REPO_README = """# Game saves

Private save-file backups managed by **{app}**.

## Layout

```
games/<game-slug>/profile.json   what this game is and where its saves live
games/<game-slug>/data/...       the save files themselves
```

Every backup is one commit. To see the history for a single game:

```
git log -- games/<game-slug>
```

To recover a save by hand, check out any commit and copy the files back.
""".format(app=APP_NAME)


@dataclass
class BackupResult:
    changed: bool
    commit_sha: str | None
    message: str
    files_uploaded: int = 0
    files_deleted: int = 0
    bytes_uploaded: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    files_written: int
    files_skipped: int
    safety_archive: Path | None
    warnings: list[str] = field(default_factory=list)


class SyncEngine:
    def __init__(self, client: GitHubClient, config: AppConfig) -> None:
        self.client = client
        self.config = config

    @property
    def owner(self) -> str:
        return self.config.repo_owner

    @property
    def repo(self) -> str:
        return self.config.repo_name

    @property
    def branch(self) -> str:
        return self.config.branch

    # ---- repo bootstrap -------------------------------------------------

    def ensure_repo(self) -> tuple[dict, bool]:
        repo, created = self.client.ensure_repo(self.owner, self.repo)
        if created:
            self.config.branch = repo.get("default_branch") or self.branch
            self._write_readme_if_missing()
        elif repo.get("default_branch"):
            self.config.branch = repo["default_branch"]
        return repo, created

    def _write_readme_if_missing(self) -> None:
        try:
            head = self.client.get_branch_head(self.owner, self.repo, self.branch)
            if head is None:
                return
            commit = self.client.get_commit(self.owner, self.repo, head)
            entries, _ = self.client.get_tree(
                self.owner, self.repo, commit["tree"]["sha"], recursive=False
            )
            existing = {e.path for e in entries}
            if "README.md" in existing:
                return
            blob = self.client.create_blob(
                self.owner, self.repo, REPO_README.encode("utf-8")
            )
            tree = self.client.create_tree(
                self.owner,
                self.repo,
                [{"path": "README.md", "mode": FILE_MODE, "type": "blob", "sha": blob}],
                base_tree=commit["tree"]["sha"],
            )
            new_commit = self.client.create_commit(
                self.owner, self.repo, "Describe repo layout", tree, [head]
            )
            self.client.update_ref(self.owner, self.repo, self.branch, new_commit)
        except GitHubError:
            # Cosmetic only — never fail a setup over the README.
            pass

    # ---- backup ---------------------------------------------------------

    def backup(
        self,
        profile: GameProfile,
        progress: Progress | None = None,
        _attempt: int = 0,
    ) -> BackupResult:
        def report(pct: int, text: str) -> None:
            if progress:
                progress(pct, text)

        report(2, "Reading save files…")
        snapshot = collect(profile)

        if snapshot.is_empty:
            if snapshot.missing_sources:
                missing = ", ".join(snapshot.missing_sources)
                raise GitHubError(f"None of the configured paths exist: {missing}")
            raise GitHubError("No files matched this game's paths (all excluded?).")

        report(12, "Checking what's already backed up…")
        head = self.client.get_branch_head(self.owner, self.repo, self.branch)
        if head is None:
            raise GitHubError(
                f"Branch '{self.branch}' does not exist in {self.owner}/{self.repo}."
            )
        commit = self.client.get_commit(self.owner, self.repo, head)
        root_tree = commit["tree"]["sha"]
        remote_entries = self._remote_entries(root_tree)

        prefix = profile.repo_dir + "/"
        existing = {
            e.path[len(prefix) :]: e.sha
            for e in remote_entries
            if e.type == "blob" and e.path.startswith(prefix)
        }

        desired: dict[str, bytes] = {f.repo_path: f.data for f in snapshot.files}
        desired_sha = {f.repo_path: f.sha for f in snapshot.files}

        profile_json = (
            json.dumps(profile.to_repo_dict(), indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        desired["profile.json"] = profile_json
        desired_sha["profile.json"] = git_blob_sha(profile_json)

        changed = [p for p, sha in desired_sha.items() if existing.get(p) != sha]
        removed = [p for p in existing if p not in desired_sha]

        if not changed and not removed:
            return BackupResult(
                changed=False,
                commit_sha=head,
                message="Already up to date — no save changes since the last backup.",
                warnings=snapshot.warnings,
            )

        # profile.json alone changing is bookkeeping, not a save change; still
        # commit it, but say so honestly.
        only_metadata = changed == ["profile.json"] and not removed

        tree_entries: list[dict] = []
        uploaded_bytes = 0
        for index, rel in enumerate(changed):
            data = desired[rel]
            pct = 20 + int(60 * (index / max(len(changed), 1)))
            report(pct, f"Uploading {rel.rsplit('/', 1)[-1]}…")
            blob_sha = self.client.create_blob(self.owner, self.repo, data)
            uploaded_bytes += len(data)
            tree_entries.append(
                {
                    "path": f"{prefix}{rel}",
                    "mode": FILE_MODE,
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        for rel in removed:
            tree_entries.append(
                {
                    "path": f"{prefix}{rel}",
                    "mode": FILE_MODE,
                    "type": "blob",
                    "sha": None,
                }
            )

        report(85, "Committing…")
        new_tree = self.client.create_tree(
            self.owner, self.repo, tree_entries, base_tree=root_tree
        )
        message = self._commit_message(profile, len(changed), len(removed), only_metadata)
        new_commit = self.client.create_commit(
            self.owner, self.repo, message, new_tree, [head]
        )

        try:
            self.client.update_ref(self.owner, self.repo, self.branch, new_commit)
        except GitHubError as exc:
            # Another machine committed between our read and write. Rebuild
            # against the new head once; a second failure is a real problem.
            if _attempt == 0 and exc.status in (409, 422):
                report(90, "Another device pushed first — retrying…")
                return self.backup(profile, progress, _attempt=1)
            raise

        report(100, "Done")
        profile.last_backup_at = iso_now()
        profile.last_commit_sha = new_commit
        profile.last_status = "ok"
        profile.last_error = ""

        if only_metadata:
            summary = "Saved settings — no save-file changes"
        elif changed:
            summary = (
                f"Backed up {len(changed)} file{'s' if len(changed) != 1 else ''}"
                f" ({humanize_bytes(uploaded_bytes)})"
            )
            if removed:
                summary += f", removed {len(removed)}"
        else:
            summary = f"Removed {len(removed)} deleted file{'s' if len(removed) != 1 else ''}"

        return BackupResult(
            changed=True,
            commit_sha=new_commit,
            message=summary,
            files_uploaded=len(changed),
            files_deleted=len(removed),
            bytes_uploaded=uploaded_bytes,
            warnings=snapshot.warnings,
        )

    def _commit_message(
        self, profile: GameProfile, changed: int, removed: int, only_metadata: bool
    ) -> str:
        stamp = utc_now().astimezone().strftime("%Y-%m-%d %H:%M")
        host = platform.node() or "unknown-device"
        if only_metadata:
            headline = f"{profile.name}: update profile"
        else:
            bits = []
            if changed:
                bits.append(f"{changed} changed")
            if removed:
                bits.append(f"{removed} removed")
            headline = f"{profile.name}: backup ({', '.join(bits)})"
        return f"{headline}\n\n{stamp} on {host}"

    def _remote_entries(self, tree_sha: str) -> list[TreeEntry]:
        entries, truncated = self.client.get_tree(self.owner, self.repo, tree_sha)
        if not truncated:
            return entries
        # Very large repos truncate the recursive listing; walk it manually.
        return self._walk_tree(tree_sha, "")

    def _walk_tree(self, tree_sha: str, prefix: str) -> list[TreeEntry]:
        out: list[TreeEntry] = []
        entries, _ = self.client.get_tree(
            self.owner, self.repo, tree_sha, recursive=False
        )
        for entry in entries:
            path = f"{prefix}{entry.path}"
            if entry.type == "tree" and entry.sha:
                out.extend(self._walk_tree(entry.sha, f"{path}/"))
            else:
                out.append(
                    TreeEntry(path, entry.mode, entry.type, entry.sha, entry.size)
                )
        return out

    # ---- history & restore ----------------------------------------------

    def history(self, profile: GameProfile, limit: int = 50) -> list[CommitInfo]:
        return self.client.list_commits(
            self.owner,
            self.repo,
            path=profile.repo_dir,
            branch=self.branch,
            limit=limit,
        )

    def list_backed_up_files(
        self, profile: GameProfile, commit_sha: str
    ) -> list[TreeEntry]:
        commit = self.client.get_commit(self.owner, self.repo, commit_sha)
        entries = self._remote_entries(commit["tree"]["sha"])
        prefix = profile.data_prefix
        return [e for e in entries if e.type == "blob" and e.path.startswith(prefix)]

    def restore(
        self,
        profile: GameProfile,
        commit_sha: str,
        *,
        progress: Progress | None = None,
        make_safety_copy: bool = True,
    ) -> RestoreResult:
        def report(pct: int, text: str) -> None:
            if progress:
                progress(pct, text)

        report(5, "Fetching backup contents…")
        blobs = self.list_backed_up_files(profile, commit_sha)
        if not blobs:
            raise GitHubError("That backup contains no files for this game.")

        prefix = profile.repo_dir + "/"
        warnings: list[str] = []
        planned: list[tuple[Path, str]] = []  # (target, blob sha)

        for entry in blobs:
            rel = entry.path[len(prefix) :]
            target, reason = resolve_restore_target(profile, rel)
            if target is None:
                warnings.append(f"Skipped {rel} — {reason}.")
                continue
            planned.append((target, entry.sha or ""))

        if not planned:
            raise GitHubError(
                "Could not map any backed-up file to a location on this machine. "
                "Check the game's paths in Edit."
            )

        archive: Path | None = None
        if make_safety_copy:
            report(15, "Saving a copy of your current files…")
            archive = self._make_safety_archive(profile)

        written = 0
        for index, (target, blob_sha) in enumerate(planned):
            pct = 25 + int(70 * (index / max(len(planned), 1)))
            report(pct, f"Restoring {target.name}…")
            try:
                data = self.client.get_blob(self.owner, self.repo, blob_sha)
            except GitHubError as exc:
                warnings.append(f"Could not download {target.name}: {exc}")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".gss-tmp")
                tmp.write_bytes(data)
                tmp.replace(target)
                written += 1
            except OSError as exc:
                warnings.append(f"Could not write {target}: {exc}")

        report(100, "Done")
        return RestoreResult(
            files_written=written,
            files_skipped=len(blobs) - written,
            safety_archive=archive,
            warnings=warnings,
        )

    def _make_safety_archive(self, profile: GameProfile) -> Path | None:
        snapshot: Snapshot = collect(profile)
        if snapshot.is_empty:
            return None
        stamp = utc_now().strftime("%Y%m%d-%H%M%S")
        path = safety_dir() / f"{profile.slug}-{stamp}.zip"
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in snapshot.files:
                    zf.writestr(entry.repo_path, entry.data)
        except OSError:
            return None
        return path
