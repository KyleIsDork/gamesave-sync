"""Opening URLs and folders in the user's browser or file manager.

``QDesktopServices.openUrl`` returns a bool that is easy to ignore, and when it
fails it does so silently: the user clicks a button and nothing at all happens.
It also fails more often in a frozen build, because PyInstaller and the AppImage
AppRun both export loader variables that leak into any child process. A browser
started with those inherited can fail to launch.

So every call goes through here, which checks the return value, falls back
through progressively more manual mechanisms, and tells the caller whether
anything worked.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

# Variables the PyInstaller bootloader and the AppImage AppRun set for the
# bundled interpreter. A child process must not inherit them, or it will try to
# load our bundled libraries instead of the system ones.
_BUNDLE_VARS = (
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "QT_PLUGIN_PATH",
    "QML2_IMPORT_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "GTK_PATH",
    "GDK_PIXBUF_MODULE_FILE",
)


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) or "APPDIR" in os.environ


def child_environment() -> dict[str, str]:
    """A copy of the environment safe to hand to an external program.

    PyInstaller saves the pre-launch value of each variable it overrides as
    ``<NAME>_ORIG``; where that exists it is restored, otherwise the variable is
    dropped entirely.
    """
    env = dict(os.environ)
    for name in _BUNDLE_VARS:
        original = env.pop(f"{name}_ORIG", None)
        if original:
            env[name] = original
        else:
            env.pop(name, None)
    return env


def _launcher_command(target: str) -> list[str] | None:
    if sys.platform == "win32":
        return ["cmd", "/c", "start", "", target]
    if sys.platform == "darwin":
        return ["open", target]
    return ["xdg-open", target]


def _spawn(target: str) -> bool:
    command = _launcher_command(target)
    if not command:
        return False
    try:
        subprocess.Popen(
            command,
            env=child_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(sys.platform != "win32"),
        )
    except (OSError, ValueError):
        return False
    return True


def open_url(url: str) -> bool:
    """Open a web URL. Returns True if something plausibly handled it."""
    # Qt first: it integrates with the desktop portal and works under Flatpak.
    try:
        if QDesktopServices.openUrl(QUrl(url)):
            return True
    except Exception:
        pass

    # The platform launcher, with the bundle's loader variables stripped.
    if _spawn(url):
        return True

    try:
        return webbrowser.open(url)
    except Exception:
        return False


def open_folder(path: Path | str) -> bool:
    """Reveal a local directory in the file manager."""
    target = Path(path)
    try:
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            return True
    except Exception:
        pass
    return _spawn(str(target))
