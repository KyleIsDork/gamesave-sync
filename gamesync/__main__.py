"""Entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QDialog

from . import APP_NAME
from .github import GitHubClient
from .store import load_config, load_token, save_config
from .ui.main_window import MainWindow
from .ui.onboarding import ConnectDialog
from .ui.theme import stylesheet


def main() -> int:
    # Started by the login autostart entry: come up hidden in the tray rather
    # than throwing a window at the user every time they log in.
    background = "--background" in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("gamesave-sync")

    # Qt's default point size is small on some Linux setups; nudge it up without
    # overriding a user's deliberate system scaling.
    font = app.font()
    if font.pointSizeF() < 10:
        font.setPointSizeF(10)
    app.setFont(font)

    config = load_config()
    app.setStyleSheet(stylesheet(config.theme))

    client: GitHubClient | None = None
    token = load_token()
    if token and config.repo_owner:
        client = GitHubClient(token)
    elif not background:
        dialog = ConnectDialog(config)
        dialog.setStyleSheet(stylesheet(config.theme))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            client = dialog.client
            save_config(config)
        # Declining just opens the app unconnected; Settings can connect later.

    window = MainWindow(config, client)

    if background and window.tray is not None:
        # Quitting the last window must not end the process while we live in
        # the tray with no window shown.
        app.setQuitOnLastWindowClosed(False)
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
