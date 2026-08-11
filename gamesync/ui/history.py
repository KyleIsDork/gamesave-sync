"""Browse a game's backup history and restore one."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..github import CommitInfo
from ..models import GameProfile
from ..util import humanize_since, parse_iso
from .widgets import Spinner


class HistoryDialog(QDialog):
    """Lists commits touching this game. Restore is delegated to the caller so
    it runs on the shared worker queue rather than blocking the dialog."""

    restore_requested = Signal(str, bool)  # commit sha, make_safety_copy

    def __init__(self, profile: GameProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle(f"History: {profile.name}")
        self.setMinimumSize(620, 520)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 20)
        root.setSpacing(12)

        title = QLabel(f"{self.profile.name} backups")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Every backup is a commit. Restoring writes those files back over "
            "your current saves."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.status_row = QHBoxLayout()
        self.spinner = Spinner(15)
        self.status_label = QLabel("Loading history…")
        self.status_label.setObjectName("Hint")
        self.status_row.addWidget(self.spinner)
        self.status_row.addWidget(self.status_label)
        self.status_row.addStretch(1)
        root.addLayout(self.status_row)

        self.listing = QListWidget()
        self.listing.itemSelectionChanged.connect(self._selection_changed)
        self.listing.itemDoubleClicked.connect(lambda _: self._restore())
        root.addWidget(self.listing, 1)

        self.safety_check = QCheckBox(
            "Save a zip of my current files first (recommended)"
        )
        self.safety_check.setChecked(True)
        root.addWidget(self.safety_check)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        self.restore_button = QPushButton("Restore this backup")
        self.restore_button.setObjectName("Primary")
        self.restore_button.setEnabled(False)
        self.restore_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_button.clicked.connect(self._restore)
        buttons.addWidget(close)
        buttons.addWidget(self.restore_button)
        root.addLayout(buttons)

    # ---- population ------------------------------------------------------

    def set_loading(self, loading: bool) -> None:
        if loading:
            self.spinner.start()
            self.status_label.setText("Loading history…")
        else:
            self.spinner.stop()

    def set_commits(self, commits: list[CommitInfo]) -> None:
        self.set_loading(False)
        self.listing.clear()

        if not commits:
            self.status_label.setText(
                "No backups yet for this game. Run a backup first."
            )
            return

        self.status_label.setText(
            f"{len(commits)} backup{'s' if len(commits) != 1 else ''}, newest first"
        )
        for index, commit in enumerate(commits):
            headline = commit.message.splitlines()[0] if commit.message else commit.sha[:7]
            when = parse_iso(commit.date)
            stamp = when.astimezone().strftime("%d %b %Y, %H:%M") if when else commit.date
            relative = humanize_since(commit.date)
            label = f"{stamp}   ·   {relative}"
            if index == 0:
                label += "   ·   latest"
            item = QListWidgetItem(f"{label}\n{headline}")
            item.setData(Qt.ItemDataRole.UserRole, commit.sha)
            item.setToolTip(f"{commit.sha}\n\n{commit.message}")
            self.listing.addItem(item)

    def set_error(self, message: str) -> None:
        self.set_loading(False)
        self.status_label.setText(f"Could not load history: {message}")

    # ---- actions ---------------------------------------------------------

    def _selection_changed(self) -> None:
        self.restore_button.setEnabled(bool(self.listing.selectedItems()))

    def _restore(self) -> None:
        item = self.listing.currentItem()
        if not item:
            return
        sha = item.data(Qt.ItemDataRole.UserRole)

        safety = self.safety_check.isChecked()
        detail = (
            "Your current files will be zipped to the app's data folder first."
            if safety
            else "Your current files will be overwritten with no local copy kept."
        )
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Restore this backup?")
        confirm.setText(
            f"Restore {self.profile.name} from this backup?"
        )
        confirm.setInformativeText(detail + "\n\nClose the game before restoring.")
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        confirm.button(QMessageBox.StandardButton.Ok).setText("Restore")
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if confirm.exec() != QMessageBox.StandardButton.Ok:
            return

        self.restore_requested.emit(sha, safety)
        self.accept()
