"""Discovering Steam libraries and installed games.

Steam records where everything lives in two kinds of file:

``steamapps/libraryfolders.vdf``
    Every library folder, including ones on other drives. Without reading this,
    a game installed to a secondary disk is invisible.

``steamapps/appmanifest_<appid>.acf``
    One per installed game, giving its name and install directory.

Both are Valve's KeyValues format: quoted "key" "value" pairs and nested braces.
It is small and regular enough to parse directly, which avoids a dependency for
what amounts to twenty lines.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_KV_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s*"((?:[^"\\]|\\.)*)"')


def parse_vdf(text: str) -> dict:
    """Parse Valve KeyValues into nested dicts.

    Duplicate keys keep the last value, which matches how Steam itself reads
    these files.
    """
    root: dict = {}
    stack: list[dict] = [root]
    pending_key: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue

        if line == "{":
            child: dict = {}
            if pending_key is not None:
                stack[-1][pending_key] = child
                pending_key = None
            stack.append(child)
            continue

        if line == "}":
            if len(stack) > 1:
                stack.pop()
            continue

        match = _KV_PAIR.match(line)
        if match:
            key, value = match.group(1), match.group(2)
            stack[-1][key.lower()] = value.replace("\\\\", "\\")
            pending_key = None
            continue

        if line.startswith('"') and line.endswith('"'):
            pending_key = line[1:-1].lower()

    return root


def steam_roots() -> list[Path]:
    """Candidate Steam installation directories for this OS."""
    home = Path.home()
    candidates: list[Path] = []

    if sys.platform == "win32":
        program_files = [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        ]
        candidates += [p / "Steam" for p in program_files]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Steam")
    elif sys.platform == "darwin":
        candidates.append(home / "Library" / "Application Support" / "Steam")
    else:
        candidates += [
            home / ".local" / "share" / "Steam",
            home / ".steam" / "steam",
            home / ".steam" / "root",
            home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        ]

    seen: set[Path] = set()
    roots = []
    for c in candidates:
        if c.exists() and c not in seen:
            seen.add(c)
            roots.append(c)
    return roots


def library_folders() -> list[Path]:
    """Every Steam library folder on this machine.

    Includes libraries on secondary drives, which is the whole point: a default
    install path guess misses them entirely.
    """
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path).rstrip("/\\").lower()
        if path.exists() and key not in seen:
            seen.add(key)
            found.append(path)

    for root in steam_roots():
        add(root)

        manifest = root / "steamapps" / "libraryfolders.vdf"
        if not manifest.exists():
            continue
        try:
            data = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue

        # Both the modern ("libraryfolders" -> "0" -> {"path": ...}) and the
        # older flat ("0": "<path>") layouts appear in the wild.
        section = data.get("libraryfolders", data)
        if not isinstance(section, dict):
            continue
        for value in section.values():
            if isinstance(value, dict):
                path = value.get("path")
            elif isinstance(value, str):
                path = value
            else:
                path = None
            if path:
                add(Path(path))

    return found


@dataclass
class SteamGame:
    appid: str
    name: str
    install_dir: str
    library: Path
    manifest: Path = field(repr=False, default_factory=Path)

    @property
    def install_path(self) -> Path:
        return self.library / "steamapps" / "common" / self.install_dir

    @property
    def compat_prefix(self) -> Path:
        """The Proton prefix for this game, where a Windows build keeps its files."""
        return (
            self.library
            / "steamapps"
            / "compatdata"
            / self.appid
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
        )


def installed_games() -> list[SteamGame]:
    """Every installed Steam game found across all libraries."""
    games: list[SteamGame] = []
    seen: set[str] = set()

    for library in library_folders():
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue

        for manifest in manifests:
            try:
                data = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            state = data.get("appstate")
            if not isinstance(state, dict):
                continue
            appid = state.get("appid") or ""
            if not appid or appid in seen:
                continue
            seen.add(appid)
            games.append(
                SteamGame(
                    appid=str(appid),
                    name=state.get("name", f"App {appid}"),
                    install_dir=state.get("installdir", ""),
                    library=library,
                    manifest=manifest,
                )
            )

    return sorted(games, key=lambda g: g.name.lower())


def find_by_appid(appid: str) -> SteamGame | None:
    return next((g for g in installed_games() if g.appid == str(appid)), None)


def compat_prefix_for(appid: str) -> Path | None:
    """Proton prefix for an installed appid, searched across every library."""
    for library in library_folders():
        prefix = (
            library
            / "steamapps"
            / "compatdata"
            / str(appid)
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
        )
        if prefix.exists():
            return prefix
    return None
