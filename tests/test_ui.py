"""Headless UI construction and state tests.

These build real widgets under Qt's offscreen platform. They catch the class of
breakage that matters most here: a signal wired to a method that no longer
exists, or a status that reports the wrong thing.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gamesync.models import AppConfig, GameProfile, Source  # noqa: E402
from gamesync.ui.main_window import MainWindow  # noqa: E402
from gamesync.ui.theme import stylesheet  # noqa: E402
from gamesync.util import iso_now, utc_now  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def populated_config(tmp_path):
    saves = tmp_path / "HollowKnight"
    saves.mkdir()
    (saves / "user1.dat").write_bytes(b"x" * 128)

    config = AppConfig(repo_owner="tester", repo_name="game-saves")
    config.games = [
        GameProfile(
            name="Hollow Knight",
            slug="hollow-knight",
            sources=[Source(path=str(saves), kind="dir")],
            interval_minutes=30,
            last_backup_at=iso_now(),
        ),
        GameProfile(
            name="Terraria",
            slug="terraria",
            sources=[Source(path=str(saves), kind="dir")],
            interval_minutes=60,
        ),
        GameProfile(
            name="Balatro",
            slug="balatro",
            sources=[Source(path="{APPDATA}/Balatro", kind="dir")],
            enabled=False,
        ),
        GameProfile(
            name="Elden Ring",
            slug="elden-ring",
            sources=[Source(path=str(saves), kind="dir")],
            last_status="error",
            last_error="rate limited",
        ),
    ]
    return config


@pytest.fixture
def window(qapp, populated_config, monkeypatch, tmp_path):
    # Never write the developer's real config from a test.
    monkeypatch.setattr("gamesync.ui.main_window.save_config", lambda cfg: None)

    win = MainWindow(populated_config, client=None)
    win.scheduler.stop()
    yield win
    win.runner.shutdown()
    win.deleteLater()


def test_window_builds_a_card_per_game(window):
    assert len(window.cards) == 4


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("hollow-knight", "Synced"),
        ("terraria", "Never backed up"),
        ("balatro", "Paused"),
        ("elden-ring", "Failed"),
    ],
)
def test_status_pill_reflects_profile_state(window, slug, expected):
    assert window.cards[slug].status_pill.text() == expected


def test_busy_state_disables_actions_and_restores(window):
    card = window.cards["hollow-knight"]

    card.set_busy(True, "Uploading…", 40)
    assert not card.backup_button.isEnabled()
    # isVisible() is False until an ancestor window is shown; isHidden()
    # reflects the explicit show/hide state, which is what we set.
    assert not card.progress.isHidden()
    assert card.activity_label.text() == "Uploading…"
    assert card.status_pill.text() == "Working"

    card.set_busy(False)
    assert card.backup_button.isEnabled()
    assert card.progress.isHidden()
    assert card.status_pill.text() == "Synced"


def test_empty_state_shown_when_no_games(qapp, monkeypatch):
    monkeypatch.setattr("gamesync.ui.main_window.save_config", lambda cfg: None)
    win = MainWindow(AppConfig(repo_owner="tester"), client=None)
    win.scheduler.stop()
    try:
        assert not win.cards
        assert not win.games_empty.isHidden()
        assert win.games_scroll.isHidden()
    finally:
        win.runner.shutdown()


def test_backup_without_a_connection_redirects_to_settings(window):
    window.backup_all()
    assert window.pages.currentIndex() == 2


def test_scheduler_honours_the_interval(window, populated_config):
    profile = populated_config.games[1]  # Terraria, 60 minutes
    window._schedule_next(profile)

    due = window._next_due[profile.slug]
    delta = (due - utc_now()).total_seconds()
    assert 3500 < delta < 3700


def test_failure_backoff_extends_the_interval(window, populated_config):
    profile = populated_config.games[1]
    window._schedule_next(profile, backoff=True)

    delta = (window._next_due[profile.slug] - utc_now()).total_seconds()
    assert delta > 7000


def test_disabling_a_game_clears_its_schedule(window):
    window.toggle_game("terraria", False)
    assert "terraria" not in window._next_due


def test_enabling_a_game_restores_its_schedule(window):
    window.toggle_game("terraria", False)
    window.toggle_game("terraria", True)
    assert "terraria" in window._next_due


def test_manual_only_games_are_never_scheduled(window, populated_config):
    profile = populated_config.games[0]
    profile.interval_minutes = 0
    window._schedule_next(profile)
    assert profile.slug not in window._next_due


def test_activity_log_is_capped(window):
    from gamesync.ui.main_window import MAX_ACTIVITY_ROWS

    for i in range(MAX_ACTIVITY_ROWS + 25):
        window.log_activity(f"entry {i}")

    assert window.activity_list.count() == MAX_ACTIVITY_ROWS
    # Newest first.
    assert "entry 224" in window.activity_list.item(0).text()


def test_theme_switch_updates_config_and_picker(window):
    window.apply_theme("light")
    assert window.config.theme == "light"
    assert window.theme_combo.currentData() == "light"

    window.apply_theme("dark")
    assert window.theme_combo.currentData() == "dark"


def test_page_switch_syncs_sidebar_highlight(window):
    window.pages.setCurrentIndex(2)
    assert window.nav_group.button(2).isChecked()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_stylesheet_builds_for_both_themes(qapp, theme):
    sheet = stylesheet(theme)
    assert "QPushButton" in sheet
    assert "%(" not in sheet  # every placeholder was substituted
