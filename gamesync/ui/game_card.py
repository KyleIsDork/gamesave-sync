"""The per-game row on the Games page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import GameProfile
from ..paths import expand
from ..util import humanize_interval, humanize_since, plural
from .widgets import Card, Pill


class GameCard(Card):
    backup_requested = Signal(str)
    history_requested = Signal(str)
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    toggle_requested = Signal(str, bool)

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slug = profile.slug
        self.profile = profile
        self._build()
        self.update_profile(profile)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        self.name_label = QLabel()
        self.name_label.setObjectName("SectionTitle")
        name_font = self.name_label.font()
        name_font.setPointSizeF(name_font.pointSizeF() + 1.5)
        self.name_label.setFont(name_font)

        self.detail_label = QLabel()
        self.detail_label.setObjectName("Hint")
        text_col.addWidget(self.name_label)
        text_col.addWidget(self.detail_label)

        self.status_pill = Pill("", "neutral")

        top.addLayout(text_col, 1)
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)

        self.backup_button = QPushButton("Back up now")
        self.backup_button.setObjectName("Primary")
        self.backup_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backup_button.clicked.connect(
            lambda: self.backup_requested.emit(self.slug)
        )

        self.history_button = QPushButton("History")
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.clicked.connect(
            lambda: self.history_requested.emit(self.slug)
        )

        self.menu_button = QPushButton("⋯")
        self.menu_button.setObjectName("Ghost")
        self.menu_button.setFixedWidth(34)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.clicked.connect(self._show_menu)

        top.addWidget(self.backup_button)
        top.addWidget(self.history_button)
        top.addWidget(self.menu_button)
        outer.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.hide()
        outer.addWidget(self.progress)

        self.activity_label = QLabel()
        self.activity_label.setObjectName("Hint")
        self.activity_label.hide()
        outer.addWidget(self.activity_label)

    # ---- state -----------------------------------------------------------

    def update_profile(self, profile: GameProfile) -> None:
        self.profile = profile
        self.name_label.setText(profile.name)

        source_count = len(profile.sources)
        missing = sum(1 for s in profile.sources if not expand(s.path).exists())
        bits = [plural(source_count, "location")]
        if profile.interval_minutes and profile.enabled:
            bits.append(humanize_interval(profile.interval_minutes))
        elif not profile.enabled:
            bits.append("auto-backup off")
        else:
            bits.append("manual only")
        bits.append(f"last backup {humanize_since(profile.last_backup_at)}")
        if missing:
            bits.append(f"{plural(missing, 'path')} missing")
        self.detail_label.setText("  ·  ".join(bits))

        if profile.last_status == "error":
            self.status_pill.set_state("Failed", "danger")
            self.status_pill.setToolTip(profile.last_error)
        elif not profile.enabled:
            # A deliberate pause outranks the missing-path warning; the detail
            # line still mentions the missing paths.
            self.status_pill.set_state("Paused", "neutral")
            self.status_pill.setToolTip("")
        elif missing == source_count and source_count:
            self.status_pill.set_state("Not on this PC", "warn")
            self.status_pill.setToolTip(
                "None of this game's save paths exist here. Edit it to point at "
                "the right folders."
            )
        elif profile.last_backup_at:
            self.status_pill.set_state("Synced", "success")
            self.status_pill.setToolTip("")
        else:
            self.status_pill.set_state("Never backed up", "warn")
            self.status_pill.setToolTip("")

    def apply_theme(self, theme: str) -> None:
        self.status_pill.apply_theme(theme)

    def set_busy(self, busy: bool, text: str = "", percent: int = 0) -> None:
        self.backup_button.setEnabled(not busy)
        self.history_button.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.activity_label.setVisible(busy)
        if busy:
            self.progress.setValue(percent)
            self.activity_label.setText(text)
            self.status_pill.set_state("Working", "accent")
        else:
            self.update_profile(self.profile)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        toggle_text = (
            "Pause automatic backups"
            if self.profile.enabled
            else "Resume automatic backups"
        )
        toggle_action = menu.addAction(toggle_text)
        edit_action = menu.addAction("Edit…")
        menu.addSeparator()
        remove_action = menu.addAction("Remove from this app")

        chosen = menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))
        if chosen == toggle_action:
            self.toggle_requested.emit(self.slug, not self.profile.enabled)
        elif chosen == edit_action:
            self.edit_requested.emit(self.slug)
        elif chosen == remove_action:
            self.remove_requested.emit(self.slug)
