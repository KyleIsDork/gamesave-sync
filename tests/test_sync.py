"""Backup and restore behaviour, against an in-memory fake of the git data API."""

from __future__ import annotations

import pytest

from gamesync.github import GitHubError
from gamesync.models import GameProfile, Source
from gamesync.sync import SyncEngine


@pytest.fixture
def engine(fake_github, config, profile):
    config.games.append(profile)
    return SyncEngine(fake_github, config)


def test_first_backup_commits_expected_files(engine, fake_github, profile):
    result = engine.backup(profile)

    assert result.changed
    assert sorted(fake_github.head_tree()) == [
        "games/my-game/data/saves/nested/meta.json",
        "games/my-game/data/saves/slot1.dat",
        "games/my-game/data/saves/slot2.dat",
        "games/my-game/profile.json",
    ]


def test_default_excludes_drop_log_files(engine, fake_github, profile):
    engine.backup(profile)
    assert not any("debug.log" in path for path in fake_github.head_tree())


def test_unchanged_backup_uploads_nothing_and_makes_no_commit(
    engine, fake_github, profile
):
    engine.backup(profile)
    head_before = fake_github.refs["main"]
    uploads_before = fake_github.blob_uploads

    result = engine.backup(profile)

    assert not result.changed
    assert fake_github.blob_uploads == uploads_before
    assert fake_github.refs["main"] == head_before


def test_only_changed_blobs_are_uploaded(engine, fake_github, profile, save_dir):
    engine.backup(profile)
    uploads_before = fake_github.blob_uploads

    (save_dir / "slot1.dat").write_bytes(b"first save EDITED")
    result = engine.backup(profile)

    assert result.changed
    assert result.files_uploaded == 1
    assert fake_github.blob_uploads - uploads_before == 1


def test_deletions_propagate_to_the_tree(engine, fake_github, profile, save_dir):
    engine.backup(profile)

    (save_dir / "slot2.dat").unlink()
    result = engine.backup(profile)

    assert result.files_deleted == 1
    assert "games/my-game/data/saves/slot2.dat" not in fake_github.head_tree()
    assert "Removed 1 deleted file" in result.message


def test_history_lists_backups_newest_first(engine, profile, save_dir):
    engine.backup(profile)
    (save_dir / "slot1.dat").write_bytes(b"v2")
    engine.backup(profile)

    history = engine.history(profile)

    assert len(history) >= 2
    assert history[0].message.startswith("My Game")


def test_restore_returns_files_to_an_earlier_state(
    engine, profile, save_dir, isolated_dirs
):
    engine.backup(profile)
    original = engine.history(profile)[0].sha

    (save_dir / "slot1.dat").write_bytes(b"CORRUPTED")
    (save_dir / "slot2.dat").unlink()

    result = engine.restore(profile, original, make_safety_copy=False)

    assert result.files_written == 3
    assert (save_dir / "slot1.dat").read_bytes() == b"first save"
    assert (save_dir / "slot2.dat").read_bytes() == b"second save"
    assert (save_dir / "nested" / "meta.json").read_text() == '{"a":1}'


def test_restore_writes_a_safety_archive_first(
    engine, profile, save_dir, isolated_dirs
):
    engine.backup(profile)
    sha = engine.history(profile)[0].sha
    (save_dir / "slot1.dat").write_bytes(b"CORRUPTED")

    result = engine.restore(profile, sha, make_safety_copy=True)

    assert result.safety_archive is not None
    assert result.safety_archive.exists()

    import zipfile

    with zipfile.ZipFile(result.safety_archive) as zf:
        # The archive holds the pre-restore (corrupted) content, which is the
        # whole point of taking it.
        assert zf.read("data/saves/slot1.dat") == b"CORRUPTED"


def test_single_file_source_round_trips(fake_github, config, tmp_path, isolated_dirs):
    target = tmp_path / "OtherGame" / "profile.sav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"v1")

    profile = GameProfile(
        name="Other Game", sources=[Source(path=str(target), kind="file")]
    )
    config.games.append(profile)
    engine = SyncEngine(fake_github, config)

    engine.backup(profile)
    target.write_bytes(b"CORRUPTED")
    engine.restore(profile, engine.history(profile)[0].sha, make_safety_copy=False)

    assert target.read_bytes() == b"v1"


def test_backup_retries_after_losing_a_ref_race(fake_github, config, profile):
    """Another machine committing mid-backup should not lose the backup."""
    config.games.append(profile)
    engine = SyncEngine(fake_github, config)

    original_update = fake_github.update_ref
    calls = {"n": 0}

    def flaky(owner, repo, branch, sha, force=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise GitHubError("reference cannot be updated", 422)
        return original_update(owner, repo, branch, sha, force)

    fake_github.update_ref = flaky

    result = engine.backup(profile)

    assert result.changed
    assert calls["n"] == 2


def test_backup_with_no_existing_paths_is_an_error(fake_github, config):
    profile = GameProfile(
        name="Ghost", sources=[Source(path="/nonexistent/path/xyz", kind="dir")]
    )
    config.games.append(profile)
    engine = SyncEngine(fake_github, config)

    with pytest.raises(GitHubError, match="None of the configured paths exist"):
        engine.backup(profile)


def test_profile_json_is_committed_alongside_saves(engine, fake_github, profile):
    import json

    engine.backup(profile)
    tree = fake_github.head_tree()
    stored = json.loads(fake_github.blobs[tree["games/my-game/profile.json"]])

    assert stored["name"] == "My Game"
    assert stored["slug"] == "my-game"
    assert stored["sources"]
