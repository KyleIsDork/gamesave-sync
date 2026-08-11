"""Application shell: sidebar, pages, scheduler wiring."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, VERSION
from ..autostart import is_enabled as autostart_is_enabled
from ..autostart import set_enabled as autostart_set_enabled
from ..github import GitHubClient
from ..models import AppConfig, GameProfile
from ..paths import safety_dir
from ..store import clear_token, save_config, token_storage_is_secure
from ..sync import BackupResult, RestoreResult, SyncEngine
from ..util import parse_iso, plural, utc_now
from ..worker import Job, JobRunner
from .game_card import GameCard
from .game_editor import GameEditorDialog
from .history import HistoryDialog
from .links import open_folder, open_url
from .onboarding import ConnectDialog
from .theme import stylesheet
from .widgets import Card, Divider, EmptyState, Toast

SCHEDULER_TICK_MS = 30_000
MAX_ACTIVITY_ROWS = 200


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig, client: GitHubClient | None) -> None:
        super().__init__()
        self.config = config
        self.client = client
        self.engine = SyncEngine(client, config) if client else None
        self.cards: dict[str, GameCard] = {}
        self._open_history: HistoryDialog | None = None
        self._next_due: dict[str, object] = {}

        self.setWindowTitle(APP_NAME)
        self.resize(1020, 720)
        self.setMinimumSize(840, 560)

        self.runner = JobRunner(self)
        self.runner.job_started.connect(self._on_job_started)
        self.runner.job_progress.connect(self._on_job_progress)
        self.runner.job_finished.connect(self._on_job_finished)
        self.runner.job_failed.connect(self._on_job_failed)
        self.runner.start()

        self._build()
        self.apply_theme(self.config.theme)
        self.refresh_games()
        self._refresh_account()

        self.scheduler = QTimer(self)
        self.scheduler.timeout.connect(self._scheduler_tick)
        self.scheduler.start(SCHEDULER_TICK_MS)
        self._seed_schedule()

        if not token_storage_is_secure() and self.client:
            self.log_activity(
                "Token stored in a file, no system keychain was available.", "warn"
            )

        self._force_quit = False
        self._tray_hint_shown = False
        self.tray: QSystemTrayIcon | None = None
        self._setup_tray()

        if self.config.backup_on_launch and self.client:
            QTimer.singleShot(1500, lambda: self.backup_all(silent=True))

    # ---- layout ----------------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_games_page())
        self.pages.addWidget(self._build_activity_page())
        self.pages.addWidget(self._build_settings_page())
        # Keep the sidebar highlight correct even when a page is switched in
        # code (e.g. redirecting to Settings when there is no connection).
        self.pages.currentChanged.connect(self._sync_nav_highlight)
        layout.addWidget(self.pages, 1)

        self.setCentralWidget(root)
        self.toast = Toast(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(228)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(4)

        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("BrandTitle")
        subtitle = QLabel("save backups on GitHub")
        subtitle.setObjectName("BrandSub")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        wrapper = QWidget()
        wrapper.setLayout(brand)
        wrapper.setContentsMargins(6, 0, 0, 10)
        layout.addWidget(wrapper)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (label, _) in enumerate(
            [("Games", ""), ("Activity", ""), ("Settings", "")]
        ):
            button = QPushButton(label)
            button.setObjectName("NavItem")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self.pages.setCurrentIndex(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)
        self.nav_group.button(0).setChecked(True)

        layout.addStretch(1)

        self.sync_status = QLabel("")
        self.sync_status.setObjectName("Hint")
        self.sync_status.setWordWrap(True)
        self.sync_status.setContentsMargins(6, 0, 0, 6)
        layout.addWidget(self.sync_status)

        self.account_chip = QWidget()
        self.account_chip.setObjectName("AccountChip")
        self.account_chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chip_layout = QVBoxLayout(self.account_chip)
        chip_layout.setContentsMargins(11, 9, 11, 9)
        chip_layout.setSpacing(2)
        self.account_label = QLabel("Not connected")
        self.account_label.setObjectName("SectionTitle")
        self.repo_label = QLabel("")
        self.repo_label.setObjectName("Hint")
        self.repo_label.setWordWrap(True)
        chip_layout.addWidget(self.account_label)
        chip_layout.addWidget(self.repo_label)
        layout.addWidget(self.account_chip)

        return sidebar

    def _page_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout, QHBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        text_col.addWidget(heading)
        text_col.addWidget(sub)
        header.addLayout(text_col, 1)
        layout.addLayout(header)

        return page, layout, header

    def _build_games_page(self) -> QWidget:
        page, layout, header = self._page_shell(
            "Games", "Each game is backed up to its own folder in your private repo."
        )

        self.backup_all_button = QPushButton("Back up all")
        self.backup_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_all_button.clicked.connect(lambda: self.backup_all())
        add_button = QPushButton("Add game")
        add_button.setObjectName("Primary")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self.add_game)
        header.addWidget(self.backup_all_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(add_button, 0, Qt.AlignmentFlag.AlignTop)

        self.games_scroll = QScrollArea()
        self.games_scroll.setWidgetResizable(True)
        self.games_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        container = QWidget()
        self.games_layout = QVBoxLayout(container)
        # Right gutter reserves room for the scrollbar so cards keep their width
        # whether or not the list overflows.
        self.games_layout.setContentsMargins(1, 1, 13, 1)
        self.games_layout.setSpacing(10)
        self.games_layout.addStretch(1)
        self.games_scroll.setWidget(container)
        layout.addWidget(self.games_scroll, 1)

        self.games_empty = EmptyState(
            "🎮",
            "No games yet",
            "Add a game and point it at the folder its saves live in. "
            "The app can detect a few common ones for you.",
            "Add your first game",
        )
        self.games_empty.action_clicked.connect(self.add_game)
        layout.addWidget(self.games_empty, 1)

        return page

    def _build_activity_page(self) -> QWidget:
        page, layout, header = self._page_shell(
            "Activity", "What this app has done, most recent first."
        )

        open_repo = QPushButton("Open repo on GitHub")
        open_repo.setCursor(Qt.CursorShape.PointingHandCursor)
        open_repo.clicked.connect(self.open_repo)
        header.addWidget(open_repo, 0, Qt.AlignmentFlag.AlignTop)

        self.activity_list = QListWidget()
        layout.addWidget(self.activity_list, 1)

        return page

    def _build_settings_page(self) -> QWidget:
        page, layout, _ = self._page_shell(
            "Settings", "Account, schedule, and appearance."
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 6, 0)
        body_layout.setSpacing(12)

        # -- account
        account_card = Card()
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(18, 16, 18, 16)
        account_layout.setSpacing(10)
        account_title = QLabel("GitHub account")
        account_title.setObjectName("SectionTitle")
        self.settings_account = QLabel("")
        self.settings_account.setObjectName("Hint")
        self.settings_account.setWordWrap(True)
        account_buttons = QHBoxLayout()
        reconnect = QPushButton("Reconnect / change token")
        reconnect.clicked.connect(self.reconnect)
        disconnect = QPushButton("Sign out")
        disconnect.setObjectName("Danger")
        disconnect.clicked.connect(self.sign_out)
        account_buttons.addWidget(reconnect)
        account_buttons.addWidget(disconnect)
        account_buttons.addStretch(1)
        account_layout.addWidget(account_title)
        account_layout.addWidget(self.settings_account)
        account_layout.addLayout(account_buttons)
        body_layout.addWidget(account_card)

        # -- backups
        backup_card = Card()
        backup_layout = QVBoxLayout(backup_card)
        backup_layout.setContentsMargins(18, 16, 18, 16)
        backup_layout.setSpacing(10)
        backup_title = QLabel("Backups")
        backup_title.setObjectName("SectionTitle")
        backup_layout.addWidget(backup_title)

        self.auto_check = QCheckBox("Run scheduled backups while the app is open")
        self.auto_check.setChecked(self.config.auto_backup)
        self.auto_check.toggled.connect(self._set_auto_backup)
        backup_layout.addWidget(self.auto_check)

        self.launch_check = QCheckBox("Back up everything when the app starts")
        self.launch_check.setChecked(self.config.backup_on_launch)
        self.launch_check.toggled.connect(self._set_backup_on_launch)
        backup_layout.addWidget(self.launch_check)

        backup_layout.addWidget(Divider())

        background_title = QLabel("Running in the background")
        background_title.setObjectName("SectionTitle")
        backup_layout.addWidget(background_title)

        self.tray_check = QCheckBox("Keep running in the tray when I close the window")
        self.tray_check.setChecked(self.config.minimize_to_tray)
        self.tray_check.toggled.connect(self._set_minimize_to_tray)
        backup_layout.addWidget(self.tray_check)

        self.login_check = QCheckBox("Start GameSave Sync when I log in")
        # Read the real state rather than trusting config: the user may have
        # removed the entry outside the app.
        self.config.start_at_login = autostart_is_enabled()
        self.login_check.setChecked(self.config.start_at_login)
        self.login_check.toggled.connect(self._set_start_at_login)
        backup_layout.addWidget(self.login_check)

        self.background_hint = QLabel("")
        self.background_hint.setObjectName("Hint")
        self.background_hint.setWordWrap(True)
        backup_layout.addWidget(self.background_hint)

        backup_layout.addWidget(Divider())
        note = QLabel(
            "A backup only creates a commit when a save file actually changed, "
            "so idle games cost nothing."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        backup_layout.addWidget(note)

        safety_row = QHBoxLayout()
        safety_label = QLabel("Pre-restore copies are kept on this machine.")
        safety_label.setObjectName("Hint")
        open_safety = QPushButton("Open folder")
        open_safety.setObjectName("LinkButton")
        open_safety.setCursor(Qt.CursorShape.PointingHandCursor)
        open_safety.clicked.connect(self.open_safety_folder)
        safety_row.addWidget(safety_label)
        safety_row.addWidget(open_safety)
        safety_row.addStretch(1)
        backup_layout.addLayout(safety_row)
        body_layout.addWidget(backup_card)

        # -- appearance
        appearance_card = Card()
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(10)
        appearance_title = QLabel("Appearance")
        appearance_title.setObjectName("SectionTitle")
        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_label.setObjectName("Dim")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.setCurrentIndex(0 if self.config.theme == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(
            lambda: self.apply_theme(self.theme_combo.currentData(), persist=True)
        )
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo, 1)
        appearance_layout.addWidget(appearance_title)
        appearance_layout.addLayout(theme_row)
        body_layout.addWidget(appearance_card)

        version = QLabel(f"{APP_NAME} {VERSION}")
        version.setObjectName("Hint")
        body_layout.addWidget(version)
        body_layout.addStretch(1)

        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        return page

    # ---- theming ---------------------------------------------------------

    def _sync_nav_highlight(self, index: int) -> None:
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)

    def apply_theme(self, theme: str, persist: bool = False) -> None:
        self.config.theme = theme
        self.setStyleSheet(stylesheet(theme))
        self.toast.apply_theme(theme)
        for card in self.cards.values():
            card.apply_theme(theme)

        # Keep the picker in step when the theme is set from elsewhere.
        index = self.theme_combo.findData(theme)
        if index >= 0 and index != self.theme_combo.currentIndex():
            blocked = self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(blocked)

        if persist:
            self._save()

    # ---- games list ------------------------------------------------------

    def refresh_games(self) -> None:
        for card in self.cards.values():
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()

        has_games = bool(self.config.games)
        self.games_scroll.setVisible(has_games)
        self.games_empty.setVisible(not has_games)
        self.backup_all_button.setEnabled(has_games)

        for profile in self.config.games:
            card = GameCard(profile)
            card.apply_theme(self.config.theme)
            card.backup_requested.connect(self.backup_game)
            card.history_requested.connect(self.show_history)
            card.edit_requested.connect(self.edit_game)
            card.remove_requested.connect(self.remove_game)
            card.toggle_requested.connect(self.toggle_game)
            self.cards[profile.slug] = card
            self.games_layout.insertWidget(self.games_layout.count() - 1, card)

        self._update_sync_status()

    def add_game(self) -> None:
        if not self._require_connection():
            return
        dialog = GameEditorDialog(self.config, None, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        profile = dialog.result_profile()
        profile.slug = self.config.unique_slug(profile.name)
        self.config.games.append(profile)
        self._save()
        self.refresh_games()
        self._schedule_next(profile, first=True)
        self.log_activity(f"Added {profile.name}.", "success")
        self.show_toast(f"{profile.name} added, running the first backup.", "success")
        self.backup_game(profile.slug)

    def edit_game(self, slug: str) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile:
            return
        dialog = GameEditorDialog(self.config, profile, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._save()
        self.refresh_games()
        self.log_activity(f"Updated {profile.name}.")

    def remove_game(self, slug: str) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile:
            return
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Remove game?")
        confirm.setText(f"Stop backing up {profile.name}?")
        confirm.setInformativeText(
            "Your existing backups stay in the GitHub repo, this only removes "
            "the game from this app."
        )
        confirm.setIcon(QMessageBox.Icon.Question)
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        confirm.button(QMessageBox.StandardButton.Ok).setText("Remove")
        if confirm.exec() != QMessageBox.StandardButton.Ok:
            return

        self.config.games = [g for g in self.config.games if g.slug != slug]
        self._next_due.pop(slug, None)
        self._save()
        self.refresh_games()
        self.log_activity(f"Removed {profile.name} from the app.")

    def toggle_game(self, slug: str, enabled: bool) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile:
            return
        profile.enabled = enabled
        self._save()
        if enabled:
            self._schedule_next(profile)
        else:
            self._next_due.pop(slug, None)
        card = self.cards.get(slug)
        if card:
            card.update_profile(profile)
        self._update_sync_status()

    # ---- jobs ------------------------------------------------------------

    def backup_game(self, slug: str, silent: bool = False) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile or not self.engine:
            return

        def run(report, _profile=profile):
            return self.engine.backup(_profile, report)

        job = Job(kind="backup", label=f"Backing up {profile.name}", fn=run, slug=slug)
        job.meta["silent"] = silent
        if not self.runner.submit(job, dedupe_key=f"backup:{slug}"):
            return
        card = self.cards.get(slug)
        if card:
            card.set_busy(True, "Queued…", 0)

    def backup_all(self, silent: bool = False) -> None:
        if not self._require_connection(quiet=silent):
            return
        targets = [g for g in self.config.games if g.enabled and g.sources]
        if not targets:
            if not silent:
                self.show_toast("No games are set to back up.", "warn")
            return
        for profile in targets:
            self.backup_game(profile.slug, silent=silent)
        if not silent:
            self.show_toast(f"Backing up {plural(len(targets), 'game')}…")

    def show_history(self, slug: str) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile or not self.engine or not self._require_connection():
            return

        dialog = HistoryDialog(profile, self)
        dialog.setStyleSheet(stylesheet(self.config.theme))
        dialog.set_loading(True)
        dialog.restore_requested.connect(
            lambda sha, safety, s=slug: self.restore_game(s, sha, safety)
        )
        self._open_history = dialog

        def run(report, _profile=profile):
            report(50, "Loading history…")
            return self.engine.history(_profile)

        job = Job(kind="history", label="Loading history", fn=run, slug=slug)
        self.runner.submit(job)
        dialog.exec()
        self._open_history = None

    def restore_game(self, slug: str, commit_sha: str, safety: bool) -> None:
        profile = self.config.game_by_slug(slug)
        if not profile or not self.engine:
            return

        def run(report, _profile=profile):
            return self.engine.restore(
                _profile, commit_sha, progress=report, make_safety_copy=safety
            )

        job = Job(kind="restore", label=f"Restoring {profile.name}", fn=run, slug=slug)
        self.runner.submit(job, dedupe_key=f"restore:{slug}")
        card = self.cards.get(slug)
        if card:
            card.set_busy(True, "Restoring…", 0)

    # ---- job signal handlers ---------------------------------------------

    def _on_job_started(self, job: Job) -> None:
        card = self.cards.get(job.slug)
        if card and job.kind in ("backup", "restore"):
            card.set_busy(True, job.label + "…", 2)
        self._update_sync_status()

    def _on_job_progress(self, job: Job, percent: int, text: str) -> None:
        card = self.cards.get(job.slug)
        if card and job.kind in ("backup", "restore"):
            card.set_busy(True, text, percent)

    def _on_job_finished(self, job: Job, result: object) -> None:
        card = self.cards.get(job.slug)
        profile = self.config.game_by_slug(job.slug)

        if job.kind == "history":
            if self._open_history:
                self._open_history.set_commits(result)  # type: ignore[arg-type]
            return

        if card:
            card.set_busy(False)

        if job.kind == "backup" and isinstance(result, BackupResult):
            if profile:
                self._save()
                card and card.update_profile(profile)
                self._schedule_next(profile)
            name = profile.name if profile else job.slug
            if result.changed:
                self.log_activity(f"{name}: {result.message}", "success")
                if not job.meta.get("silent"):
                    self.show_toast(f"{name}: {result.message}", "success")
            else:
                self.log_activity(f"{name}: no changes.")
            for warning in result.warnings:
                self.log_activity(f"{name}: {warning}", "warn")

        elif job.kind == "restore" and isinstance(result, RestoreResult):
            name = profile.name if profile else job.slug
            message = f"Restored {plural(result.files_written, 'file')}"
            if result.safety_archive:
                message += f", previous files zipped to {result.safety_archive.name}"
            self.log_activity(f"{name}: {message}", "success")
            self.show_toast(f"{name} restored.", "success")
            for warning in result.warnings:
                self.log_activity(f"{name}: {warning}", "warn")

        self._update_sync_status()

    def _on_job_failed(self, job: Job, message: str) -> None:
        card = self.cards.get(job.slug)
        profile = self.config.game_by_slug(job.slug)

        if job.kind == "history":
            if self._open_history:
                self._open_history.set_error(message)
            return

        if card:
            card.set_busy(False)

        if profile and job.kind == "backup":
            profile.last_status = "error"
            profile.last_error = message
            self._save()
            if card:
                card.update_profile(profile)
            self._schedule_next(profile, backoff=True)

        name = profile.name if profile else job.label
        self.log_activity(f"{name}: {message}", "danger")
        if not job.meta.get("silent"):
            self.show_toast(f"{name}: {message}", "danger", msec=7000)
        self._update_sync_status()

    # ---- scheduler -------------------------------------------------------

    def _seed_schedule(self) -> None:
        for profile in self.config.games:
            self._schedule_next(profile, first=True)

    def _schedule_next(
        self, profile: GameProfile, first: bool = False, backoff: bool = False
    ) -> None:
        if not profile.enabled or not profile.interval_minutes:
            self._next_due.pop(profile.slug, None)
            return

        minutes = profile.interval_minutes
        if backoff:
            # A failing game should not hammer the API every interval.
            minutes = max(minutes, 15) * 2

        base = utc_now()
        if first and profile.last_backup_at:
            last = parse_iso(profile.last_backup_at)
            if last:
                base = max(last, utc_now() - timedelta(minutes=minutes))
        self._next_due[profile.slug] = base + timedelta(minutes=minutes)

    def _scheduler_tick(self) -> None:
        if not self.config.auto_backup or not self.engine:
            return
        now = utc_now()
        for profile in self.config.games:
            if not profile.enabled or not profile.interval_minutes:
                continue
            due = self._next_due.get(profile.slug)
            if due is None:
                self._schedule_next(profile)
                continue
            if now >= due:
                # Push the next slot forward before queueing so a slow backup
                # cannot stack up behind itself.
                self._schedule_next(profile)
                self.backup_game(profile.slug, silent=True)
        self._update_sync_status()

    # ---- account ---------------------------------------------------------

    def _refresh_account(self) -> None:
        if self.client and self.config.repo_owner:
            self.account_label.setText(self.config.repo_owner)
            self.repo_label.setText(f"{self.config.repo_name} · private")
            self.settings_account.setText(
                f"Connected as {self.config.repo_owner}, syncing to "
                f"{self.config.repo_owner}/{self.config.repo_name} "
                f"(branch {self.config.branch})."
                + ("" if token_storage_is_secure() else
                   "\n\nToken is in a restricted file, not the system keychain.")
            )
        else:
            self.account_label.setText("Not connected")
            self.repo_label.setText("Connect a GitHub account in Settings")
            self.settings_account.setText("No account connected.")

    def _require_connection(self, quiet: bool = False) -> bool:
        if self.client and self.engine:
            return True
        if not quiet:
            self.show_toast("Connect a GitHub account first (Settings).", "warn")
            self.pages.setCurrentIndex(2)
            self.nav_group.button(2).setChecked(True)
        return False

    def reconnect(self) -> None:
        dialog = ConnectDialog(self.config, self)
        dialog.setStyleSheet(stylesheet(self.config.theme))
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.client:
            return
        self.client = dialog.client
        self.engine = SyncEngine(self.client, self.config)
        self._save()
        self._refresh_account()
        self.log_activity(f"Connected as {self.config.repo_owner}.", "success")
        self.show_toast("Connected to GitHub.", "success")

    def sign_out(self) -> None:
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Sign out?")
        confirm.setText("Remove the stored GitHub token?")
        confirm.setInformativeText(
            "Your games and backups are untouched. You'll need to paste a token "
            "again to resume syncing."
        )
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        if confirm.exec() != QMessageBox.StandardButton.Ok:
            return
        clear_token()
        self.client = None
        self.engine = None
        self._refresh_account()
        self.log_activity("Signed out.")

    def open_repo(self) -> None:
        if not self.config.repo_owner:
            self.show_toast("Connect an account first.", "warn")
            return
        url = f"https://github.com/{self.config.repo_owner}/{self.config.repo_name}"
        if not open_url(url):
            # Never fail silently: show the address so it can be copied.
            self.show_toast(f"Could not open a browser. The repo is at {url}", "warn", msec=9000)
            self.log_activity(f"Could not open a browser for {url}", "warn")

    def open_safety_folder(self) -> None:
        folder = safety_dir()
        if not open_folder(folder):
            self.show_toast(f"Could not open a file manager. Folder: {folder}", "warn", msec=9000)
            self.log_activity(f"Could not open a file manager for {folder}", "warn")

    # ---- system tray -----------------------------------------------------

    def app_icon(self) -> QIcon:
        """The window and tray icon, loaded from the bundle or the source tree."""
        for base in (
            Path(getattr(sys, "_MEIPASS", "")) / "assets" if getattr(sys, "_MEIPASS", "") else None,
            Path(__file__).resolve().parent.parent.parent / "assets",
        ):
            if base and (base / "icon.png").exists():
                return QIcon(str(base / "icon.png"))
        # Fall back to a plain coloured square rather than showing nothing.
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        return QIcon(pixmap)

    def _setup_tray(self) -> None:
        icon = self.app_icon()
        self.setWindowIcon(icon)

        if not QSystemTrayIcon.isSystemTrayAvailable():
            # Some minimal Linux sessions have no tray. Closing must then quit,
            # or the app would become unreachable.
            self.log_activity("No system tray available, closing will quit the app.")
            return

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        self._tray_open = QAction("Open GameSave Sync", self)
        self._tray_open.triggered.connect(self.show_from_tray)
        self._tray_backup = QAction("Back up all now", self)
        self._tray_backup.triggered.connect(lambda: self.backup_all())
        self._tray_pause = QAction("Pause automatic backups", self)
        self._tray_pause.triggered.connect(self._toggle_auto_from_tray)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)

        menu.addAction(self._tray_open)
        menu.addSeparator()
        menu.addAction(self._tray_backup)
        menu.addAction(self._tray_pause)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._refresh_tray()

        # With a tray, hiding the window must not end the process. Quitting is
        # explicit from here on, via quit_application.
        application = QApplication.instance()
        if application is not None:
            application.setQuitOnLastWindowClosed(False)

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _toggle_auto_from_tray(self) -> None:
        self.auto_check.setChecked(not self.config.auto_backup)

    def _refresh_tray(self) -> None:
        if not self.tray:
            return
        paused = not self.config.auto_backup
        self._tray_pause.setText(
            "Resume automatic backups" if paused else "Pause automatic backups"
        )
        games = len([g for g in self.config.games if g.enabled])
        state = "paused" if paused else f"{games} game(s) scheduled"
        self.tray.setToolTip(f"{APP_NAME}\n{state}")

    def quit_application(self) -> None:
        """Really exit, as opposed to hiding to the tray."""
        self._force_quit = True
        self.close()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    # ---- misc ------------------------------------------------------------

    def _set_auto_backup(self, value: bool) -> None:
        self.config.auto_backup = value
        self._save()
        self._update_sync_status()
        self._refresh_tray()

    def _set_backup_on_launch(self, value: bool) -> None:
        self.config.backup_on_launch = value
        self._save()

    def _set_minimize_to_tray(self, value: bool) -> None:
        self.config.minimize_to_tray = value
        self._save()
        if value and not self.tray:
            self.background_hint.setText(
                "This session has no system tray, so closing the window will quit."
            )
        else:
            self.background_hint.setText("")

    def _set_start_at_login(self, value: bool) -> None:
        ok, message = autostart_set_enabled(value)
        if ok:
            self.config.start_at_login = value
            self._save()
            self.background_hint.setText(message)
            self.log_activity(message)
        else:
            # Put the checkbox back where it was, the change did not take.
            blocked = self.login_check.blockSignals(True)
            self.login_check.setChecked(not value)
            self.login_check.blockSignals(blocked)
            self.background_hint.setText(message)
            self.log_activity(message, "warn")

    def _update_sync_status(self) -> None:
        pending = self.runner.pending_count()
        if pending:
            self.sync_status.setText(f"{plural(pending, 'job')} queued")
            return
        if not self.config.auto_backup:
            self.sync_status.setText("Automatic backups are off")
            return
        upcoming = [d for d in self._next_due.values() if d]
        if not upcoming:
            self.sync_status.setText("No scheduled backups")
            return
        soonest = min(upcoming)  # type: ignore[type-var]
        delta = (soonest - utc_now()).total_seconds()  # type: ignore[operator]
        if delta <= 60:
            self.sync_status.setText("Next backup: any moment")
        elif delta < 3600:
            self.sync_status.setText(f"Next backup in {int(delta // 60)} min")
        else:
            self.sync_status.setText(f"Next backup in {int(delta // 3600)} h")

    def log_activity(self, message: str, tone: str = "neutral") -> None:
        stamp = utc_now().astimezone().strftime("%H:%M")
        prefix = {"success": "✓", "warn": "!", "danger": "✗"}.get(tone, "·")
        self.activity_list.insertItem(0, f"{stamp}   {prefix}  {message}")
        while self.activity_list.count() > MAX_ACTIVITY_ROWS:
            self.activity_list.takeItem(self.activity_list.count() - 1)

    def show_toast(self, message: str, tone: str = "neutral", msec: int = 4200) -> None:
        self.toast.show_message(message, tone, msec)

    def _save(self) -> None:
        save_config(self.config)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast._reposition()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # Closing the window keeps backups running in the tray, which is the
        # whole point of the tray. Quit is explicit, via the tray menu.
        if self.tray and self.config.minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self.tray.showMessage(
                    APP_NAME,
                    "Still running in the tray, backups continue. "
                    "Use Quit in the tray menu to exit.",
                    self.app_icon(),
                    5000,
                )
                self._tray_hint_shown = True
            return

        self.scheduler.stop()
        self._save()
        self.runner.shutdown()
        if self.tray:
            self.tray.hide()
        super().closeEvent(event)
