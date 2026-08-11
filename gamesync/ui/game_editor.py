"""Add / edit a game: name, save locations, exclusions, backup interval."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import DEFAULT_EXCLUDES, AppConfig, GameProfile, Source
from ..paths import expand, tokenize
from ..presets import detect_installed
from ..snapshot import collect
from ..util import humanize_bytes, plural
from .widgets import Divider

INTERVAL_CHOICES = [
    ("Every 5 minutes", 5),
    ("Every 15 minutes", 15),
    ("Every 30 minutes", 30),
    ("Every hour", 60),
    ("Every 3 hours", 180),
    ("Every 6 hours", 360),
    ("Once a day", 1440),
    ("Manual only", 0),
]


class GameEditorDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        profile: GameProfile | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.original = profile
        self.is_new = profile is None
        self.profile = profile or GameProfile(
            name="", interval_minutes=config.default_interval_minutes
        )

        self.setWindowTitle("Add a game" if self.is_new else f"Edit {profile.name}")
        self.setMinimumSize(620, 620)
        self._build()
        self._load()

    # ---- construction ---------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 20)
        root.setSpacing(14)

        title = QLabel("Add a game" if self.is_new else "Edit game")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        name_row = QHBoxLayout()
        name_label = QLabel("Game name")
        name_label.setObjectName("Dim")
        name_label.setFixedWidth(110)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Hollow Knight")
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_input, 1)
        root.addLayout(name_row)

        if self.is_new:
            detect_row = QHBoxLayout()
            detect_row.addSpacing(110)
            self.detect_button = QPushButton("Detect installed games…")
            self.detect_button.setObjectName("LinkButton")
            self.detect_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.detect_button.clicked.connect(self._run_detection)
            detect_row.addWidget(self.detect_button)
            detect_row.addStretch(1)
            root.addLayout(detect_row)

        root.addWidget(Divider())

        paths_header = QHBoxLayout()
        paths_title = QLabel("Save locations")
        paths_title.setObjectName("SectionTitle")
        paths_header.addWidget(paths_title)
        paths_header.addStretch(1)
        add_folder = QPushButton("Add folder")
        add_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        add_folder.clicked.connect(self._add_folder)
        add_file = QPushButton("Add file")
        add_file.setCursor(Qt.CursorShape.PointingHandCursor)
        add_file.clicked.connect(self._add_file)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("Ghost")
        self.remove_button.clicked.connect(self._remove_selected)
        self.remove_button.setEnabled(False)
        paths_header.addWidget(add_folder)
        paths_header.addWidget(add_file)
        paths_header.addWidget(self.remove_button)
        root.addLayout(paths_header)

        self.path_list = QListWidget()
        self.path_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.path_list.setMinimumHeight(150)
        self.path_list.itemSelectionChanged.connect(
            lambda: self.remove_button.setEnabled(
                bool(self.path_list.selectedItems())
            )
        )
        root.addWidget(self.path_list)

        path_hint = QLabel(
            "Paths are stored portably (as {HOME}/…), so a profile still makes "
            "sense on another computer."
        )
        path_hint.setObjectName("Hint")
        path_hint.setWordWrap(True)
        root.addWidget(path_hint)

        root.addWidget(Divider())

        excl_title = QLabel("Exclude patterns")
        excl_title.setObjectName("SectionTitle")
        root.addWidget(excl_title)
        self.excludes_input = QLineEdit()
        self.excludes_input.setPlaceholderText("*.log, screenshots/*, Backups/*")
        root.addWidget(self.excludes_input)
        excl_hint = QLabel(
            "Comma-separated globs, matched against each file's path and name."
        )
        excl_hint.setObjectName("Hint")
        root.addWidget(excl_hint)

        root.addWidget(Divider())

        schedule_row = QHBoxLayout()
        schedule_label = QLabel("Back up")
        schedule_label.setObjectName("Dim")
        schedule_label.setFixedWidth(110)
        self.interval_combo = QComboBox()
        for text, minutes in INTERVAL_CHOICES:
            self.interval_combo.addItem(text, minutes)
        schedule_row.addWidget(schedule_label)
        schedule_row.addWidget(self.interval_combo, 1)
        root.addLayout(schedule_row)

        self.enabled_check = QCheckBox("Include in automatic backups")
        root.addWidget(self.enabled_check)

        self.summary = QLabel("")
        self.summary.setObjectName("Hint")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        root.addStretch(1)

        buttons = QHBoxLayout()
        preview = QPushButton("Preview what gets backed up")
        preview.setObjectName("Ghost")
        preview.clicked.connect(self._preview)
        buttons.addWidget(preview)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Add game" if self.is_new else "Save changes")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    # ---- data in / out --------------------------------------------------

    def _load(self) -> None:
        self.name_input.setText(self.profile.name)
        for source in self.profile.sources:
            self._append_source(source)

        custom = [e for e in self.profile.excludes if e not in DEFAULT_EXCLUDES]
        self.excludes_input.setText(", ".join(custom))

        index = self.interval_combo.findData(self.profile.interval_minutes)
        if index < 0:
            self.interval_combo.addItem(
                f"Every {self.profile.interval_minutes} minutes",
                self.profile.interval_minutes,
            )
            index = self.interval_combo.count() - 1
        self.interval_combo.setCurrentIndex(index)
        self.enabled_check.setChecked(self.profile.enabled)

    def _append_source(self, source: Source) -> None:
        expanded = expand(source.path)
        exists = expanded.exists()
        glyph = "▸" if source.kind == "dir" else "▪"
        suffix = "" if exists else "   (not found on this machine)"
        item = QListWidgetItem(f"{glyph}  {source.path}{suffix}")
        item.setData(Qt.ItemDataRole.UserRole, source)
        item.setToolTip(str(expanded))
        if not exists:
            item.setForeground(Qt.GlobalColor.gray)
        self.path_list.addItem(item)

    def _current_sources(self) -> list[Source]:
        return [
            self.path_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.path_list.count())
        ]

    def _add_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Select the folder containing your saves", str(Path.home())
        )
        if directory:
            self._add_path(Path(directory), "dir")

    def _add_file(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select save files", str(Path.home())
        )
        for f in files:
            self._add_path(Path(f), "file")

    def _add_path(self, path: Path, kind: str) -> None:
        tokenized = tokenize(path)
        if any(s.path == tokenized for s in self._current_sources()):
            return
        self._append_source(Source(path=tokenized, kind=kind))
        if not self.name_input.text().strip():
            self.name_input.setText(path.stem if kind == "file" else path.name)

    def _remove_selected(self) -> None:
        for item in self.path_list.selectedItems():
            self.path_list.takeItem(self.path_list.row(item))

    def _run_detection(self) -> None:
        found = detect_installed()
        if not found:
            QMessageBox.information(
                self,
                "Nothing detected",
                "No known save folders were found on this machine. "
                "Add the folder manually with “Add folder”.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Detected games")
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        heading = QLabel("Found these on your machine")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        listing = QListWidget()
        for detection in found:
            item = QListWidgetItem(detection.preset.name)
            item.setData(Qt.ItemDataRole.UserRole, detection)
            item.setToolTip("\n".join(detection.existing_paths))
            listing.addItem(item)
        listing.setCurrentRow(0)
        layout.addWidget(listing)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        use = QPushButton("Use this")
        use.setObjectName("Primary")
        use.clicked.connect(dialog.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(use)
        layout.addLayout(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        item = listing.currentItem()
        if not item:
            return
        detection = item.data(Qt.ItemDataRole.UserRole)
        self.name_input.setText(detection.preset.name)
        existing = {s.path for s in self._current_sources()}
        for source in detection.to_sources():
            if source.path not in existing:
                self._append_source(source)
        if detection.preset.excludes:
            current = self.excludes_input.text().strip()
            extra = ", ".join(detection.preset.excludes)
            self.excludes_input.setText(f"{current}, {extra}" if current else extra)

    def _build_profile(self) -> GameProfile:
        name = self.name_input.text().strip()
        custom_excludes = [
            e.strip() for e in self.excludes_input.text().split(",") if e.strip()
        ]

        profile = self.original or GameProfile(name=name)
        profile.name = name
        profile.sources = self._current_sources()
        profile.excludes = list(DEFAULT_EXCLUDES) + custom_excludes
        profile.interval_minutes = self.interval_combo.currentData()
        profile.enabled = self.enabled_check.isChecked()
        if not profile.slug:
            profile.slug = self.config.unique_slug(name)
        return profile

    def _preview(self) -> None:
        if not self.path_list.count():
            self.summary.setText("Add at least one save location first.")
            return
        profile = self._build_profile()
        snapshot = collect(profile)
        parts = [
            f"{plural(len(snapshot.files), 'file')}, {humanize_bytes(snapshot.total_bytes)}"
        ]
        if snapshot.missing_sources:
            parts.append(f"{plural(len(snapshot.missing_sources), 'path')} not found")
        if snapshot.warnings:
            parts.append(snapshot.warnings[0])
        self.summary.setText("  ·  ".join(parts))

    def _save(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            self.summary.setText("Give the game a name.")
            self.name_input.setFocus()
            return
        if not self.path_list.count():
            self.summary.setText("Add at least one save location.")
            return

        clashes = [
            g
            for g in self.config.games
            if g.name.lower() == name.lower() and g is not self.original
        ]
        if clashes:
            self.summary.setText("Another game already uses that name.")
            return

        self.profile = self._build_profile()
        self.accept()

    def result_profile(self) -> GameProfile:
        return self.profile
