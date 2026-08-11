"""Portable path handling, file collection, and restore-target safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from gamesync import paths, snapshot
from gamesync.github import git_blob_sha
from gamesync.models import GameProfile, Source
from gamesync.util import humanize_bytes, matches_any, plural, slugify


def test_blob_sha_matches_git():
    # `printf 'hello world' | git hash-object --stdin`
    assert git_blob_sha(b"hello world") == "95d09f2b10159347eece71399a7e2e907ea3df4f"


def test_tokenize_expand_round_trip():
    original = Path.home() / ".config" / "some-game"
    tokenized = paths.tokenize(original)

    assert tokenized.startswith("{")
    assert paths.expand(tokenized) == original


def test_tokenize_prefers_the_longest_matching_root():
    """A path under a more specific root should not collapse to {HOME}."""
    tokens = paths.token_map()
    if "XDG_CONFIG_HOME" not in tokens:
        pytest.skip("platform without XDG_CONFIG_HOME")

    result = paths.tokenize(tokens["XDG_CONFIG_HOME"] / "game")
    assert result == "{XDG_CONFIG_HOME}/game"


def test_expand_leaves_unknown_tokens_alone():
    assert "{NOT_A_REAL_TOKEN}" in str(paths.expand("{NOT_A_REAL_TOKEN}/x"))


def test_collect_skips_excluded_and_reads_content(save_dir):
    profile = GameProfile(
        name="G", sources=[Source(path=str(save_dir), kind="dir")]
    )
    result = snapshot.collect(profile)

    names = sorted(f.repo_path for f in result.files)
    assert names == [
        "data/saves/nested/meta.json",
        "data/saves/slot1.dat",
        "data/saves/slot2.dat",
    ]
    assert result.total_bytes > 0
    assert not result.missing_sources


def test_collect_reports_missing_sources():
    profile = GameProfile(
        name="G", sources=[Source(path="/definitely/not/here", kind="dir")]
    )
    result = snapshot.collect(profile)

    assert result.is_empty
    assert result.missing_sources == ["/definitely/not/here"]


def test_custom_excludes_are_applied(save_dir):
    profile = GameProfile(
        name="G",
        sources=[Source(path=str(save_dir), kind="dir")],
        excludes=["*.dat"],
    )
    result = snapshot.collect(profile)

    assert all(not f.repo_path.endswith(".dat") for f in result.files)


def test_duplicate_source_names_get_unique_labels(tmp_path):
    """Two sources whose folders share a name must not collide in the repo."""
    first = tmp_path / "a" / "Saves"
    second = tmp_path / "b" / "Saves"
    for d in (first, second):
        d.mkdir(parents=True)
    (first / "one.dat").write_bytes(b"1")
    (second / "two.dat").write_bytes(b"2")

    profile = GameProfile(
        name="G",
        sources=[
            Source(path=str(first), kind="dir"),
            Source(path=str(second), kind="dir"),
        ],
    )
    result = snapshot.collect(profile)
    labels = {f.repo_path.split("/")[1] for f in result.files}

    assert len(labels) == 2
    assert len(result.files) == 2


@pytest.mark.parametrize(
    "evil",
    [
        "data/saves/../../../../etc/passwd",
        "data/saves/../../escape.txt",
        "data/saves//absolute",
    ],
)
def test_restore_refuses_paths_escaping_the_source_root(save_dir, evil):
    profile = GameProfile(
        name="G", sources=[Source(path=str(save_dir), kind="dir")]
    )
    target, reason = snapshot.resolve_restore_target(profile, evil)

    assert target is None, f"should have refused {evil}"
    assert reason


def test_restore_target_resolves_normal_paths(save_dir):
    profile = GameProfile(
        name="G", sources=[Source(path=str(save_dir), kind="dir")]
    )
    target, reason = snapshot.resolve_restore_target(
        profile, "data/saves/nested/meta.json"
    )

    assert target == save_dir / "nested" / "meta.json"
    assert reason == ""


def test_restore_target_unknown_label_is_reported(save_dir):
    profile = GameProfile(
        name="G", sources=[Source(path=str(save_dir), kind="dir")]
    )
    target, reason = snapshot.resolve_restore_target(profile, "data/other/x.dat")

    assert target is None
    assert "no source" in reason


@pytest.mark.parametrize(
    "path,patterns,expected",
    [
        ("a/b/c.log", ["*.log"], True),
        ("a/b/c.dat", ["*.log"], False),
        ("Backups/old.sav", ["Backups/*"], True),
        ("node_modules/x/y", ["node_modules"], True),
        (".git/config", [".git"], True),
    ],
)
def test_exclusion_matching(path, patterns, expected):
    assert matches_any(path, patterns) is expected


def test_slugify_handles_punctuation_and_accents():
    assert slugify("Baldur's Gate 3") == "baldur-s-gate-3"
    assert slugify("NieR: Automata") == "nier-automata"
    assert slugify("!!!") == "game"


def test_plural():
    assert plural(1, "file") == "1 file"
    assert plural(2, "file") == "2 files"


def test_humanize_bytes():
    assert humanize_bytes(512) == "512 B"
    assert humanize_bytes(2048) == "2.0 KB"
