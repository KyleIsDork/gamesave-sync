"""Registering the app to start when the user logs in.

Each platform has its own mechanism and none of them are hard, but the launch
command is the fiddly part: a frozen build must relaunch its own bundle, not the
Python interpreter that no longer exists on the user's PATH.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from . import APP_NAME, APP_SLUG

BUNDLE_ID = "io.github.kyleisdork.gamesavesync"


def launch_command() -> list[str]:
    """The command that starts this app again, however it was installed."""
    # An AppImage exports APPIMAGE with the path to the .AppImage file itself.
    # sys.executable would point inside the extracted mount, which disappears.
    appimage = os.environ.get("APPIMAGE")
    if appimage and Path(appimage).exists():
        return [appimage]

    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        # On macOS, launch the .app rather than the inner binary so it gets a
        # proper application session.
        for parent in executable.parents:
            if parent.suffix == ".app":
                return ["open", "-a", str(parent)]
        return [str(executable)]

    # Running from source.
    return [sys.executable, "-m", "gamesync"]


def _quote(command: list[str]) -> str:
    if sys.platform == "win32":
        return " ".join(f'"{part}"' if " " in part else part for part in command)
    return " ".join(shlex.quote(part) for part in command)


# ---- Linux -----------------------------------------------------------------


def _linux_entry() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / f"{APP_SLUG}.desktop"


def _linux_enable() -> bool:
    entry = _linux_entry()
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Back up game saves to a private GitHub repository\n"
        f"Exec={_quote(launch_command())} --background\n"
        f"Icon={APP_SLUG}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
    return True


# ---- macOS -----------------------------------------------------------------


def _macos_entry() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"


def _macos_enable() -> bool:
    entry = _macos_entry()
    entry.parent.mkdir(parents=True, exist_ok=True)
    arguments = "".join(
        f"        <string>{part}</string>\n" for part in launch_command() + ["--background"]
    )
    entry.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{BUNDLE_ID}</string>\n"
        "    <key>ProgramArguments</key>\n"
        f"    <array>\n{arguments}    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n",
        encoding="utf-8",
    )
    return True


# ---- Windows ---------------------------------------------------------------

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_enable() -> bool:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(
            key, APP_NAME, 0, winreg.REG_SZ, f"{_quote(launch_command())} --background"
        )
    return True


def _windows_disable() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass
    return True


def _windows_is_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
    except (FileNotFoundError, OSError):
        return False
    return True


# ---- public API ------------------------------------------------------------


def is_enabled() -> bool:
    try:
        if sys.platform == "win32":
            return _windows_is_enabled()
        entry = _macos_entry() if sys.platform == "darwin" else _linux_entry()
        return entry.exists()
    except Exception:
        return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    """Turn login autostart on or off.

    Returns (succeeded, message). Failure is reported rather than raised: this
    is a convenience setting and should never take the app down with it.
    """
    try:
        if enabled:
            if sys.platform == "win32":
                _windows_enable()
            elif sys.platform == "darwin":
                _macos_enable()
            else:
                _linux_enable()
            return True, "GameSave Sync will start when you log in."

        if sys.platform == "win32":
            _windows_disable()
        else:
            entry = _macos_entry() if sys.platform == "darwin" else _linux_entry()
            entry.unlink(missing_ok=True)
        return True, "GameSave Sync will no longer start automatically."
    except Exception as exc:
        return False, f"Could not change the startup setting: {exc}"
