"""External link launching and login autostart."""

from __future__ import annotations

import sys

import pytest

from gamesync import autostart
from gamesync.ui import links


# ---- links -----------------------------------------------------------------


def test_child_environment_drops_bundle_variables(monkeypatch):
    """A browser must not inherit the bundle's loader paths."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/bundle/lib")
    monkeypatch.setenv("QT_PLUGIN_PATH", "/tmp/bundle/plugins")

    env = links.child_environment()

    assert "LD_LIBRARY_PATH" not in env
    assert "QT_PLUGIN_PATH" not in env


def test_child_environment_restores_pyinstaller_originals(monkeypatch):
    """PyInstaller saves the pre-launch value as <NAME>_ORIG."""
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/bundle/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/original")

    env = links.child_environment()

    assert env["LD_LIBRARY_PATH"] == "/usr/lib/original"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_open_url_returns_true_when_qt_succeeds(monkeypatch):
    monkeypatch.setattr(links.QDesktopServices, "openUrl", staticmethod(lambda u: True))
    assert links.open_url("https://example.com") is True


def test_open_url_falls_back_when_qt_fails(monkeypatch):
    """The whole point: a False from Qt must not be swallowed."""
    monkeypatch.setattr(links.QDesktopServices, "openUrl", staticmethod(lambda u: False))
    spawned = []
    monkeypatch.setattr(links, "_spawn", lambda target: spawned.append(target) or True)

    assert links.open_url("https://example.com") is True
    assert spawned == ["https://example.com"]


def test_open_url_falls_back_to_webbrowser(monkeypatch):
    monkeypatch.setattr(links.QDesktopServices, "openUrl", staticmethod(lambda u: False))
    monkeypatch.setattr(links, "_spawn", lambda target: False)
    called = []
    monkeypatch.setattr(links.webbrowser, "open", lambda u: called.append(u) or True)

    assert links.open_url("https://example.com") is True
    assert called == ["https://example.com"]


def test_open_url_reports_total_failure(monkeypatch):
    """When nothing works the caller must be able to tell the user."""
    monkeypatch.setattr(links.QDesktopServices, "openUrl", staticmethod(lambda u: False))
    monkeypatch.setattr(links, "_spawn", lambda target: False)
    monkeypatch.setattr(links.webbrowser, "open", lambda u: False)

    assert links.open_url("https://example.com") is False


def test_open_url_survives_a_qt_exception(monkeypatch):
    def boom(url):
        raise RuntimeError("no platform integration")

    monkeypatch.setattr(links.QDesktopServices, "openUrl", staticmethod(boom))
    monkeypatch.setattr(links, "_spawn", lambda target: True)

    assert links.open_url("https://example.com") is True


# ---- autostart -------------------------------------------------------------


def test_launch_command_prefers_the_appimage_path(monkeypatch, tmp_path):
    appimage = tmp_path / "GameSave-Sync.AppImage"
    appimage.write_text("")
    monkeypatch.setenv("APPIMAGE", str(appimage))

    assert autostart.launch_command() == [str(appimage)]


def test_launch_command_from_source(monkeypatch):
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert autostart.launch_command() == [sys.executable, "-m", "gamesync"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX autostart entry")
def test_enable_and_disable_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("APPIMAGE", raising=False)

    assert autostart.is_enabled() is False

    ok, _ = autostart.set_enabled(True)
    assert ok
    assert autostart.is_enabled() is True

    ok, _ = autostart.set_enabled(False)
    assert ok
    assert autostart.is_enabled() is False


@pytest.mark.skipif(sys.platform != "linux", reason="checks the .desktop entry")
def test_autostart_entry_passes_background_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    autostart.set_enabled(True)

    entry = tmp_path / "config" / "autostart" / "gamesave-sync.desktop"
    content = entry.read_text()

    assert "--background" in content, "must start hidden, not throw up a window at login"
    assert "Type=Application" in content


def test_set_enabled_reports_failure_instead_of_raising(monkeypatch):
    def boom():
        raise OSError("read-only filesystem")

    monkeypatch.setattr(autostart, "_linux_enable", boom)
    monkeypatch.setattr(autostart, "_macos_enable", boom)
    monkeypatch.setattr(autostart, "_windows_enable", boom)

    ok, message = autostart.set_enabled(True)

    assert ok is False
    assert "Could not change" in message
