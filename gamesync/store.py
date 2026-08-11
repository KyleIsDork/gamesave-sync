"""Config persistence and GitHub token storage.

The token goes in the OS keychain via ``keyring``. Some Linux setups have no
usable backend; rather than failing, we fall back to a 0600 file in the config
dir and tell the user that is what happened.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from . import APP_SLUG
from .models import AppConfig
from .paths import config_file, config_dir

KEYRING_SERVICE = APP_SLUG
KEYRING_USER = "github-token"

_FALLBACK_TOKEN_FILE = "token.secret"


def _fallback_path() -> Path:
    return config_dir() / _FALLBACK_TOKEN_FILE


def load_config() -> AppConfig:
    path = config_file()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt config should not brick the app; keep the bad file for
        # inspection and start clean.
        try:
            path.replace(path.with_suffix(".json.corrupt"))
        except OSError:
            pass
        return AppConfig()
    return AppConfig.from_dict(data)


def save_config(config: AppConfig) -> None:
    path = config_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(config.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)


def token_storage_is_secure() -> bool:
    return not _fallback_path().exists()


def load_token() -> str | None:
    try:
        import keyring

        token = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if token:
            return token
    except Exception:
        pass

    fallback = _fallback_path()
    if fallback.exists():
        try:
            return fallback.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


def save_token(token: str) -> bool:
    """Returns True if the token landed in the OS keychain, False if the fallback was used."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
        _delete_fallback()
        return True
    except Exception:
        pass

    fallback = _fallback_path()
    fallback.write_text(token, encoding="utf-8")
    try:
        os.chmod(fallback, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return False


def clear_token() -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass
    _delete_fallback()


def _delete_fallback() -> None:
    try:
        _fallback_path().unlink(missing_ok=True)
    except OSError:
        pass
