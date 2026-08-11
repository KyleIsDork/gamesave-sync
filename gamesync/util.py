from __future__ import annotations

import fnmatch
import re
import unicodedata
from datetime import datetime, timezone

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str, fallback: str = "game") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP.sub("-", ascii_only).strip("-")
    return slug or fallback


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def humanize_since(value: str | datetime | None) -> str:
    dt = parse_iso(value) if isinstance(value, str) or value is None else value
    if dt is None:
        return "never"
    delta = (utc_now() - dt).total_seconds()
    if delta < 0:
        return "just now"
    if delta < 60:
        return "just now"
    if delta < 3600:
        n = int(delta // 60)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if delta < 86400:
        n = int(delta // 3600)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    if delta < 86400 * 30:
        n = int(delta // 86400)
        return f"{n} day{'s' if n != 1 else ''} ago"
    return dt.astimezone().strftime("%d %b %Y")


def humanize_bytes(num: int) -> str:
    step = 1024.0
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < step or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} GB"


def humanize_interval(minutes: int) -> str:
    if minutes < 60:
        return f"every {minutes} min"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"every {days} day{'s' if days != 1 else ''}"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"every {hours} hour{'s' if hours != 1 else ''}"
    return f"every {minutes} min"


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def matches_any(rel_path: str, patterns: list[str]) -> bool:
    """Glob match against the full relative path and against the basename."""
    basename = rel_path.rsplit("/", 1)[-1]
    for pattern in patterns:
        if not pattern:
            continue
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(basename, pattern):
            return True
        # Treat "node_modules" or ".git" as "everything under it", too.
        if "/" not in pattern and "*" not in pattern:
            if rel_path == pattern or rel_path.startswith(pattern + "/"):
                return True
    return False
