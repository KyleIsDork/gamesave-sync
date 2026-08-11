"""Filesystem locations and portable path tokens.

Save locations differ per machine and per OS, so paths are stored in config and in
the repo as tokenized strings (``{HOME}/.config/foo``). Expanding them happens on
whichever machine is doing the work, which is what makes a profile written on
Windows usable on Linux.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from . import APP_SLUG

# Tokens are either plain ({HOME}) or parameterised ({STEAM_COMPAT:3146520}).
_TOKEN_RE = re.compile(r"\{([A-Z_][A-Z0-9_]*)(?::([^}]*))?\}")

# Steam library paths vary per machine, so a game on a secondary drive cannot be
# expressed with a fixed root. These resolve by asking Steam where the game
# actually is, which is what makes such a profile portable across machines.
_STEAM_COMPAT = "STEAM_COMPAT"
_STEAM_APP = "STEAM_APP"

_COMPAT_RE = re.compile(
    r"(?P<lib>.*)[/\\]steamapps[/\\]compatdata[/\\](?P<appid>\d+)"
    r"[/\\]pfx[/\\]drive_c[/\\]users[/\\]steamuser(?P<tail>.*)",
    re.IGNORECASE,
)


def config_dir() -> Path:
    p = Path(user_config_dir(APP_SLUG, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    p = Path(user_data_dir(APP_SLUG, appauthor=False))
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_file() -> Path:
    return config_dir() / "config.json"


def safety_dir() -> Path:
    """Pre-restore snapshots of whatever was on disk, in case a restore is wrong."""
    p = data_dir() / "pre-restore"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_file() -> Path:
    return data_dir() / "activity.log"


def _first_existing(*candidates: Path) -> Path | None:
    for c in candidates:
        if c.exists():
            return c
    return None


def token_map() -> dict[str, Path]:
    """Token name -> directory, for the current OS. Order matters for tokenize()."""
    home = Path.home()
    m: dict[str, Path] = {}

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        m["APPDATA"] = appdata
        m["LOCALAPPDATA"] = local
        m["LOCALLOW"] = home / "AppData" / "LocalLow"
        m["DOCUMENTS"] = home / "Documents"
        m["SAVEDGAMES"] = home / "Saved Games"
        steam = _first_existing(
            Path("C:/Program Files (x86)/Steam"),
            Path("C:/Program Files/Steam"),
            local / "Steam",
        )
    elif sys.platform == "darwin":
        m["APP_SUPPORT"] = home / "Library" / "Application Support"
        m["PREFERENCES"] = home / "Library" / "Preferences"
        m["DOCUMENTS"] = home / "Documents"
        steam = _first_existing(home / "Library" / "Application Support" / "Steam")
    else:
        m["XDG_DATA_HOME"] = Path(
            os.environ.get("XDG_DATA_HOME", home / ".local" / "share")
        )
        m["XDG_CONFIG_HOME"] = Path(
            os.environ.get("XDG_CONFIG_HOME", home / ".config")
        )
        m["DOCUMENTS"] = Path(os.environ.get("XDG_DOCUMENTS_DIR", home / "Documents"))
        steam = _first_existing(
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        )

    if steam is not None:
        m["STEAM"] = steam

    # HOME last: it is a prefix of most of the above, and tokenize() prefers the
    # longest match, so ordering only matters for ties.
    m["HOME"] = home
    return m


def _resolve_parameterised(name: str, argument: str) -> str | None:
    """Resolve a token that takes an argument, e.g. {STEAM_COMPAT:3146520}."""
    # Imported lazily: steam.py touches the filesystem, and most paths never
    # need it.
    from . import steam

    if name == _STEAM_COMPAT:
        prefix = steam.compat_prefix_for(argument)
        return str(prefix) if prefix else None
    if name == _STEAM_APP:
        game = steam.find_by_appid(argument)
        return str(game.install_path) if game else None
    return None


def expand(path_str: str) -> Path:
    """Turn ``{HOME}/.config/foo`` into a real absolute path."""
    tokens = token_map()

    def sub(match: re.Match[str]) -> str:
        name, argument = match.group(1), match.group(2)
        if argument is not None:
            resolved = _resolve_parameterised(name, argument)
            return resolved if resolved else match.group(0)
        if name in tokens:
            return str(tokens[name])
        env = os.environ.get(name)
        if env:
            return env
        return match.group(0)

    expanded = _TOKEN_RE.sub(sub, str(path_str))
    return Path(os.path.expandvars(expanded)).expanduser()


def tokenize(path: Path | str) -> str:
    """Inverse of expand(): replace the longest known directory prefix with a token."""
    p = Path(path).expanduser()
    try:
        p = p.resolve(strict=False)
    except OSError:
        pass

    # A Steam Proton prefix first: its library folder is machine specific, so a
    # fixed root would not survive being synced to another computer.
    compat = _COMPAT_RE.match(p.as_posix())
    if compat:
        tail = compat.group("tail").replace("\\", "/").strip("/")
        token = f"{{{_STEAM_COMPAT}:{compat.group('appid')}}}"
        return f"{token}/{tail}" if tail else token

    best_name: str | None = None
    best_len = -1
    for name, root in token_map().items():
        try:
            root_resolved = root.resolve(strict=False)
        except OSError:
            root_resolved = root
        try:
            p.relative_to(root_resolved)
        except ValueError:
            continue
        length = len(str(root_resolved))
        if length > best_len:
            best_name, best_len = name, length

    if best_name is None:
        return p.as_posix()

    root = token_map()[best_name].resolve(strict=False)
    rel = p.relative_to(root).as_posix()
    return f"{{{best_name}}}/{rel}" if rel else f"{{{best_name}}}"


def display_path(path_str: str) -> str:
    """Tokenized path shown to the user, with the real location in mind."""
    return str(path_str)
