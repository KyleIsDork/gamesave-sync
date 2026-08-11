"""Known save locations for games with weak or no cloud sync.

Paths are tokenized. Detection just checks which ones exist on this machine, so
a wrong guess costs nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Source, current_platform
from .paths import expand


@dataclass
class Preset:
    name: str
    paths: dict[str, list[str]]  # platform -> tokenized paths
    kind: str = "dir"
    excludes: list[str] = field(default_factory=list)

    def paths_for_platform(self, platform_name: str | None = None) -> list[str]:
        return self.paths.get(platform_name or current_platform(), [])


# Steam's Proton prefix layout on Linux, where <appid> varies per game.
def _proton(appid: str, tail: str) -> str:
    return f"{{STEAM}}/steamapps/compatdata/{appid}/pfx/drive_c/users/steamuser/{tail}"


PRESETS: list[Preset] = [
    Preset(
        "Hollow Knight",
        {
            "windows": ["{APPDATA}/../LocalLow/Team Cherry/Hollow Knight"],
            "macos": ["{HOME}/Library/Application Support/unity.Team Cherry.Hollow Knight"],
            "linux": ["{XDG_CONFIG_HOME}/unity3d/Team Cherry/Hollow Knight"],
        },
    ),
    Preset(
        "Stardew Valley",
        {
            "windows": ["{APPDATA}/StardewValley/Saves"],
            "macos": ["{HOME}/.config/StardewValley/Saves"],
            "linux": ["{XDG_CONFIG_HOME}/StardewValley/Saves"],
        },
    ),
    Preset(
        "Terraria",
        {
            "windows": ["{DOCUMENTS}/My Games/Terraria"],
            "macos": ["{HOME}/Library/Application Support/Terraria"],
            "linux": ["{XDG_DATA_HOME}/Terraria"],
        },
        excludes=["Backups/*"],
    ),
    Preset(
        "Minecraft (Java)",
        {
            "windows": ["{APPDATA}/.minecraft/saves"],
            "macos": ["{HOME}/Library/Application Support/minecraft/saves"],
            "linux": ["{HOME}/.minecraft/saves"],
        },
    ),
    Preset(
        "Factorio",
        {
            "windows": ["{APPDATA}/Factorio/saves"],
            "macos": ["{HOME}/Library/Application Support/factorio/saves"],
            "linux": ["{HOME}/.factorio/saves"],
        },
    ),
    Preset(
        "RimWorld",
        {
            "windows": ["{APPDATA}/../LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Saves"],
            "macos": ["{HOME}/Library/Application Support/RimWorld/Saves"],
            "linux": ["{XDG_CONFIG_HOME}/unity3d/Ludeon Studios/RimWorld by Ludeon Studios/Saves"],
        },
    ),
    Preset(
        "The Binding of Isaac: Repentance",
        {
            "windows": ["{DOCUMENTS}/My Games/Binding of Isaac Repentance"],
            "macos": ["{HOME}/Library/Application Support/Binding of Isaac Repentance"],
            "linux": ["{HOME}/.local/share/binding of isaac repentance"],
        },
    ),
    Preset(
        "Dwarf Fortress",
        {
            "windows": ["{DOCUMENTS}/My Games/DwarfFortress/save"],
            "linux": ["{XDG_DATA_HOME}/df_linux/data/save"],
        },
    ),
    Preset(
        "Kerbal Space Program",
        {
            "windows": ["{DOCUMENTS}/My Games/Kerbal Space Program/saves"],
            "linux": ["{HOME}/.steam/steam/steamapps/common/Kerbal Space Program/saves"],
        },
    ),
    Preset(
        "Balatro",
        {
            "windows": ["{APPDATA}/Balatro"],
            "macos": ["{HOME}/Library/Application Support/Balatro"],
            "linux": [_proton("2379780", "AppData/Roaming/Balatro")],
        },
    ),
    Preset(
        "Elden Ring",
        {
            "windows": ["{APPDATA}/EldenRing"],
            "linux": [_proton("1245620", "AppData/Roaming/EldenRing")],
        },
    ),
    Preset(
        "Dark Souls III",
        {
            "windows": ["{APPDATA}/DarkSoulsIII"],
            "linux": [_proton("374320", "AppData/Roaming/DarkSoulsIII")],
        },
    ),
    Preset(
        "Cyberpunk 2077",
        {
            "windows": ["{SAVEDGAMES}/CD Projekt Red/Cyberpunk 2077"],
            "linux": [_proton("1091500", "Saved Games/CD Projekt Red/Cyberpunk 2077")],
        },
    ),
    Preset(
        "Baldur's Gate 3",
        {
            "windows": ["{LOCALAPPDATA}/Larian Studios/Baldur's Gate 3/PlayerProfiles"],
            "macos": ["{HOME}/Documents/Larian Studios/Baldur's Gate 3/PlayerProfiles"],
            "linux": [
                _proton("1086940", "AppData/Local/Larian Studios/Baldur's Gate 3/PlayerProfiles")
            ],
        },
    ),
    Preset(
        "Valheim",
        {
            "windows": ["{APPDATA}/../LocalLow/IronGate/Valheim"],
            "linux": ["{XDG_CONFIG_HOME}/unity3d/IronGate/Valheim"],
        },
    ),
    Preset(
        "Nier: Automata",
        {
            "windows": ["{DOCUMENTS}/My Games/NieR_Automata"],
            "linux": [_proton("524220", "Documents/My Games/NieR_Automata")],
        },
    ),
    Preset(
        "Slay the Spire",
        {
            "windows": ["{HOME}/AppData/LocalLow/MegaCrit/SlayTheSpire"],
            "macos": ["{HOME}/Library/Application Support/Steam/steamapps/common/SlayTheSpire/saves"],
            "linux": ["{STEAM}/steamapps/common/SlayTheSpire/saves"],
        },
    ),
    Preset(
        "Risk of Rain 2",
        {
            "windows": ["{APPDATA}/../LocalLow/Hopoo Games/Risk of Rain 2"],
            "linux": ["{XDG_CONFIG_HOME}/unity3d/Hopoo Games/Risk of Rain 2"],
        },
    ),
]


@dataclass
class Detection:
    preset: Preset
    existing_paths: list[str]

    def to_sources(self) -> list[Source]:
        return [
            Source(path=p, kind=self.preset.kind, excludes=list(self.preset.excludes))
            for p in self.existing_paths
        ]


def detect_installed() -> list[Detection]:
    """Presets whose save directory actually exists here."""
    found: list[Detection] = []
    for preset in PRESETS:
        existing = [p for p in preset.paths_for_platform() if expand(p).exists()]
        if existing:
            found.append(Detection(preset=preset, existing_paths=existing))
    return found
