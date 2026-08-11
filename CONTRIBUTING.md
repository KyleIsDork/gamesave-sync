# Contributing

Thanks for taking an interest. This is a small project; the bar is "does it work
and is it clear", not ceremony.

## Getting set up

```bash
git clone https://github.com/KyleIsDork/gamesave-sync.git
cd gamesave-sync
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Run the checks before opening a PR:

```bash
.venv/bin/pytest
.venv/bin/python -m pyflakes gamesync/
```

The UI tests need a display, or Qt's offscreen platform:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

CI runs both on Linux, Windows and macOS.

## Adding a game preset

The most useful small contribution. Add an entry to `PRESETS` in
[`gamesync/presets.py`](gamesync/presets.py):

```python
Preset(
    "Your Game",
    {
        "windows": ["{APPDATA}/YourGame/Saves"],
        "macos": ["{HOME}/Library/Application Support/YourGame"],
        "linux": ["{XDG_DATA_HOME}/YourGame"],
    },
    excludes=["*.log"],          # optional
),
```

Guidelines:

- Use path **tokens** (`{APPDATA}`, `{HOME}`, `{XDG_DATA_HOME}`, `{STEAM}`, …),
  never absolute paths.
- Point at the **narrowest folder** that holds the saves. Backing up an entire
  game install directory is not useful and will be slow.
- For Linux Proton prefixes use the `_proton("<appid>", "<tail>")` helper.
- Only include platforms you have actually verified. A wrong path costs nothing
  (detection just won't match), but a wrong *narrow* path is misleading.
- Say in the PR which platform(s) you tested on.

## Pull requests

- Branch off `main`, one topic per PR.
- Match the surrounding style: type hints, `from __future__ import annotations`,
  and comments that explain *why* rather than restating the code.
- Add or update tests when you change behaviour. The sync engine is tested
  against an in-memory fake of the GitHub git API (`tests/test_sync.py`) — no
  network access, so tests stay fast and hermetic.
- Update `CHANGELOG.md` under `[Unreleased]`.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml). The two
things that matter most: **your OS**, and **the text from the Activity tab**.

Please redact any tokens before pasting logs. The app never prints your token,
but be careful with anything you copy from elsewhere.

## Things that need doing

- Background/autostart support so backups run without the window open
- Code signing and notarisation for the macOS build
- A conflict-resolution UI for when two machines back up the same game
- More game presets

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
