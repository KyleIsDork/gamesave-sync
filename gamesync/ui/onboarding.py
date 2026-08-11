"""First-run dialog: connect a GitHub account and create the saves repo."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..github import TOKEN_SCOPE_URL, AuthError, GitHubClient, GitHubError
from ..models import AppConfig
from ..store import save_token, token_storage_is_secure
from ..sync import SyncEngine
from .widgets import Card, Divider, Spinner


class ConnectDialog(QDialog):
    """Blocking connect flow.

    Runs its network calls inline: the dialog has nothing else to do while it
    waits, and the calls are two quick requests.
    """

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.client: GitHubClient | None = None
        self.setWindowTitle(f"Connect to GitHub — {APP_NAME}")
        self.setMinimumWidth(520)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 22)
        root.setSpacing(14)

        title = QLabel("Connect your GitHub account")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            f"{APP_NAME} stores your saves in a private repository on your own "
            "account. Nothing is sent anywhere else."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addSpacing(4)

        steps = Card(inset=True)
        steps_layout = QVBoxLayout(steps)
        steps_layout.setContentsMargins(16, 14, 16, 14)
        steps_layout.setSpacing(9)

        step_one = QLabel(
            "<b>1.</b>&nbsp; Create a personal access token with the "
            "<code>repo</code> scope."
        )
        step_one.setWordWrap(True)
        open_button = QPushButton("Open GitHub token page")
        open_button.setObjectName("LinkButton")
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TOKEN_SCOPE_URL))
        )

        step_two = QLabel("<b>2.</b>&nbsp; Paste it below.")
        step_two.setWordWrap(True)

        steps_layout.addWidget(step_one)
        steps_layout.addWidget(open_button)
        steps_layout.addWidget(Divider())
        steps_layout.addWidget(step_two)
        root.addWidget(steps)

        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("ghp_… or github_pat_…")
        self.token_input.returnPressed.connect(self._connect)
        root.addWidget(self.token_input)

        repo_row = QHBoxLayout()
        repo_label = QLabel("Repository name")
        repo_label.setObjectName("Dim")
        self.repo_input = QLineEdit(self.config.repo_name)
        self.repo_input.setPlaceholderText("game-saves")
        repo_row.addWidget(repo_label)
        repo_row.addWidget(self.repo_input, 1)
        root.addLayout(repo_row)

        hint = QLabel(
            "Created as private if it doesn't exist yet. An existing repo of "
            "this name is reused."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.status = QLabel("")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        root.addStretch(1)

        buttons = QHBoxLayout()
        self.spinner = Spinner(16)
        buttons.addWidget(self.spinner)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("Primary")
        self.connect_button.setDefault(True)
        self.connect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connect_button.clicked.connect(self._connect)
        buttons.addWidget(cancel)
        buttons.addWidget(self.connect_button)
        root.addLayout(buttons)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.connect_button.setEnabled(not busy)
        self.token_input.setEnabled(not busy)
        self.repo_input.setEnabled(not busy)
        if busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        if message:
            self.status.setText(message)

    def _connect(self) -> None:
        token = self.token_input.text().strip()
        repo_name = self.repo_input.text().strip() or "game-saves"

        if not token:
            self.status.setText("Paste a token to continue.")
            return

        self._set_busy(True, "Checking token…")
        try:
            client = GitHubClient(token)
            user = client.whoami()
            login = user.get("login")
            if not login:
                raise GitHubError("GitHub did not return an account for this token.")

            self.config.repo_owner = login
            self.config.repo_name = repo_name

            self.status.setText(f"Signed in as {login}. Preparing repository…")
            engine = SyncEngine(client, self.config)
            repo, created = engine.ensure_repo()
        except AuthError as exc:
            self._set_busy(False, f"✗ {exc}")
            return
        except GitHubError as exc:
            self._set_busy(False, f"✗ {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._set_busy(False, f"✗ Unexpected error: {exc}")
            return

        secure = save_token(token)
        self.client = client
        self._set_busy(False)

        note = "Created" if created else "Using existing"
        message = f"{note} private repo {repo.get('full_name', repo_name)}."
        if not secure:
            message += (
                "\n\nNo system keychain was available, so the token was saved to a "
                "permission-restricted file in your config directory."
            )
        self.status.setText(message)
        self.accept()

    @staticmethod
    def storage_warning() -> str:
        if token_storage_is_secure():
            return ""
        return (
            "Your token is stored in a file rather than the system keychain — "
            "no keyring backend was available."
        )
