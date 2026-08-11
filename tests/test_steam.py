"""Steam library discovery and the parameterised path tokens."""

from __future__ import annotations

import pytest

from gamesync import paths, steam

LIBRARYFOLDERS = """
"libraryfolders"
{
    "0"
    {
        "path"        "%(primary)s"
        "label"       ""
        "apps"
        {
            "730"     "1234567"
        }
    }
    "1"
    {
        "path"        "%(secondary)s"
        "label"       ""
    }
}
"""

APPMANIFEST = """
"AppState"
{
    "appid"       "%(appid)s"
    "name"        "%(name)s"
    "installdir"  "%(installdir)s"
    "StateFlags"  "4"
}
"""


@pytest.fixture
def steam_tree(tmp_path, monkeypatch):
    """A primary Steam dir plus a library on a separate 'drive'."""
    primary = tmp_path / "home" / ".local" / "share" / "Steam"
    secondary = tmp_path / "mnt" / "bigdisk" / "SteamLibrary"
    (primary / "steamapps").mkdir(parents=True)
    (secondary / "steamapps").mkdir(parents=True)

    (primary / "steamapps" / "libraryfolders.vdf").write_text(
        LIBRARYFOLDERS % {"primary": primary.as_posix(), "secondary": secondary.as_posix()}
    )
    (primary / "steamapps" / "appmanifest_730.acf").write_text(
        APPMANIFEST % {"appid": "730", "name": "Counter-Strike 2", "installdir": "csgo"}
    )
    # The game we care about lives on the secondary drive.
    (secondary / "steamapps" / "appmanifest_3146520.acf").write_text(
        APPMANIFEST
        % {"appid": "3146520", "name": "WEBFISHING", "installdir": "WEBFISHING"}
    )
    prefix = (
        secondary / "steamapps" / "compatdata" / "3146520" / "pfx"
        / "drive_c" / "users" / "steamuser"
    )
    (prefix / "AppData" / "Roaming" / "Godot" / "app_userdata" / "webfishing_2_newver").mkdir(
        parents=True
    )

    monkeypatch.setattr(steam, "steam_roots", lambda: [primary])
    return primary, secondary, prefix


def test_parse_vdf_nested():
    data = steam.parse_vdf('"root"\n{\n  "a" "1"\n  "sub"\n  {\n    "b" "2"\n  }\n}\n')
    assert data["root"]["a"] == "1"
    assert data["root"]["sub"]["b"] == "2"


def test_parse_vdf_unescapes_windows_paths():
    # Steam writes Windows paths with doubled backslashes, as they appear here.
    content = '"libraryfolders"\n{\n' + r'  "path"  "D:\\Games\\Steam"' + "\n}\n"
    data = steam.parse_vdf(content)
    assert data["libraryfolders"]["path"] == r"D:\Games\Steam"


def test_library_folders_includes_secondary_drive(steam_tree):
    primary, secondary, _ = steam_tree
    libraries = steam.library_folders()

    assert primary in libraries
    assert secondary in libraries, "a library on another drive must be discovered"


def test_installed_games_spans_all_libraries(steam_tree):
    names = {g.name for g in steam.installed_games()}
    assert names == {"Counter-Strike 2", "WEBFISHING"}


def test_find_by_appid_reports_the_right_library(steam_tree):
    _, secondary, _ = steam_tree
    game = steam.find_by_appid("3146520")

    assert game is not None
    assert game.name == "WEBFISHING"
    assert game.library == secondary


def test_compat_prefix_found_on_secondary_drive(steam_tree):
    _, _, prefix = steam_tree
    assert steam.compat_prefix_for("3146520") == prefix


def test_compat_prefix_missing_returns_none(steam_tree):
    assert steam.compat_prefix_for("999999") is None


def test_steam_compat_token_expands(steam_tree):
    _, _, prefix = steam_tree
    expanded = paths.expand("{STEAM_COMPAT:3146520}/AppData/Roaming/Godot")
    assert expanded == prefix / "AppData" / "Roaming" / "Godot"


def test_steam_compat_token_round_trips(steam_tree):
    _, _, prefix = steam_tree
    real = prefix / "AppData" / "Roaming" / "Godot" / "app_userdata" / "webfishing_2_newver"

    token = paths.tokenize(real)

    assert token.startswith("{STEAM_COMPAT:3146520}"), token
    assert paths.expand(token) == real


def test_unresolvable_token_is_left_alone(steam_tree):
    """An uninstalled game must not silently expand to something wrong."""
    result = paths.expand("{STEAM_COMPAT:999999}/saves")
    assert "{STEAM_COMPAT:999999}" in str(result)


def test_webfishing_preset_resolves_through_proton(steam_tree):
    from gamesync.presets import PRESETS

    preset = next(p for p in PRESETS if p.name == "WEBFISHING")
    linux_paths = preset.paths_for_platform("linux")

    assert any("STEAM_COMPAT:3146520" in p for p in linux_paths)
    assert any(paths.expand(p).exists() for p in linux_paths)


def test_missing_steam_install_is_not_an_error(monkeypatch):
    monkeypatch.setattr(steam, "steam_roots", lambda: [])
    assert steam.library_folders() == []
    assert steam.installed_games() == []
    assert steam.compat_prefix_for("730") is None
