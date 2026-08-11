<div align="center">

<img src="assets/icon.png" alt="GameSave Sync" width="120">

# GameSave Sync

**Automatic backups of your game saves, to a private GitHub repo you own.**

For the games that never got cloud saves, or got bad ones.

[![CI](https://github.com/KyleIsDork/gamesave-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/KyleIsDork/gamesave-sync/actions/workflows/ci.yml)
[![Release](https://github.com/KyleIsDork/gamesave-sync/actions/workflows/release.yml/badge.svg)](https://github.com/KyleIsDork/gamesave-sync/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#installation)

</div>

---

## What it is

Plenty of games still keep saves in a folder on your disk and leave the rest to
you. Lose the drive, reinstall the OS, or move to a new machine, and the save is
gone. Cloud-save systems that *do* exist sometimes make it worse by silently
overwriting the newer copy with the older one.

GameSave Sync watches the folders you tell it to, and commits them to a **private
GitHub repository on your own account** on a schedule. Every backup is a commit,
so you get full history for free: if a save corrupts, you roll back to any
earlier point instead of hoping the one cloud copy is intact.

It is a normal desktop app, not a terminal tool. Your files go to your own repo.
Nothing is sent anywhere else.

## Features

- **Automatic scheduled backups**: per game, from every 5 minutes to daily
- **Full version history**: every backup is a commit; restore any previous one
- **Genuinely incremental**: unchanged saves upload nothing and create no commit
- **Restore with a safety net**: your current files are zipped before any restore
- **Game auto-detection**: finds ~18 common games' save folders on your OS
- **Cross-machine**: paths are stored portably, so a Windows profile resolves on Linux
- **Private by default**: the repo is created private; the token lives in your OS keychain
- **No `git` required**: commits are made through the GitHub API

---

## Quickstart

### 1. Install

Download the build for your OS from the [latest release](../../releases/latest):

| Platform | File | How to run |
|---|---|---|
| **Linux** | `…-x86_64.AppImage` | `chmod +x` it, then double-click or run it |
| **Windows** | `…-windows-x64.zip` | Unzip, run `GameSave Sync.exe` |
| **macOS** (Apple Silicon) | `…-macos-arm64.zip` | Unzip, drag to Applications |
| **macOS** (Intel) | `…-macos-x86_64.zip` | Unzip, drag to Applications |

Each filename also carries the version, e.g. `GameSave-Sync-0.1.0-x86_64.AppImage`.

<details>
<summary>Or run from source</summary>

```bash
git clone https://github.com/KyleIsDork/gamesave-sync.git
cd gamesave-sync
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/gamesave-sync
```

On Windows use `.venv\Scripts\pip` and `.venv\Scripts\gamesave-sync`.

</details>

> **macOS note:** the app is not code-signed yet, so Gatekeeper will block the
> first launch. Right-click the app → **Open** → **Open**, or run
> `xattr -dr com.apple.quarantine "/Applications/GameSave Sync.app"`.

### 2. Connect your GitHub account

On first launch the app asks for a **personal access token**. There's a button
that opens the GitHub page with the right scope pre-selected, or go to
[github.com/settings/tokens/new](https://github.com/settings/tokens/new?scopes=repo&description=GameSave%20Sync)
and create one with the **`repo`** scope.

Paste it in. The app creates a private repo (`game-saves` by default) or reuses
an existing one of that name.

### 3. Add a game

Click **Add game**, then either:

- press **Detect installed games…** and pick one from the list, or
- press **Add folder** and point it at the folder your saves live in

Choose a backup interval, and you're done. Use **Preview what gets backed up** if
you want to confirm what it picked up before saving.

### 4. Restore when you need it

Hit **History** on any game. Every backup is listed with its date. Pick one and
press **Restore this backup**.

> **Close the game first.** Many games hold their save files open and will write
> their in-memory state back over your restore when they exit.

---

## How it works

No local clone, and no `git` binary required. Commits are made through GitHub's
git data API (blobs → tree → commit → ref), which behaves identically on every OS
and keeps the dependency set to pure Python.

The useful consequence: the app computes each file's **git blob SHA locally**
(`sha1("blob <len>\0" + content)`) and compares it against the remote tree
*before* uploading anything. So:

- unchanged saves upload **nothing** and create **no commit**
- a backup where one file changed uploads exactly one blob
- deleted saves are removed from the tree in the same commit

An idle game costs one cheap API call per interval.

### Repository layout

One repo, one `main` branch, one folder per game:

```
games/hollow-knight/profile.json    what this game is, where its saves live
games/hollow-knight/data/…          the save files
games/stardew-valley/profile.json
games/stardew-valley/data/…
README.md                           written on first setup
```

<details>
<summary><b>Why folders per game, and not branches per game</b></summary>

Branches were considered and rejected:

- GitHub's commit API already filters by path (`/commits?path=games/hollow-knight`),
  so **per-game history is free** without splitting the repo.
- Branches would need a separate ref update per game, and restoring on a new
  machine would mean discovering which branches exist first.
- Git deduplicates by content hash regardless of branch, branches save no space.
- One `git log` shows everything you backed up today, across every game.

Since it's an ordinary repo, you can always recover by hand without this app:

```bash
git clone https://github.com/<you>/game-saves.git
git log -- games/hollow-knight        # find the backup you want
git checkout <commit> -- games/hollow-knight/data
```

</details>

### Portable paths

`C:\Users\you\AppData\Roaming\Balatro` is stored as `{APPDATA}/Balatro` and
expanded on whichever machine is doing the work, so a profile created on Windows
still resolves on Linux. Supported tokens include `{HOME}`, `{APPDATA}`,
`{LOCALAPPDATA}`, `{DOCUMENTS}`, `{SAVEDGAMES}`, `{XDG_DATA_HOME}`,
`{XDG_CONFIG_HOME}`, `{APP_SUPPORT}` and `{STEAM}`.

### Where things are stored

| What | Location |
|---|---|
| Config (games, intervals) | `~/.config/gamesave-sync/config.json`<sup>*</sup> |
| GitHub token | OS keychain (falls back to a `0600` file, the app tells you if so) |
| Pre-restore safety zips | `~/.local/share/gamesave-sync/pre-restore/`<sup>*</sup> |

<sup>*</sup> Platform-appropriate equivalents on Windows and macOS.

---

## Security

- The repo is created **private**. It is never made public by this app.
- The token is stored via [`keyring`](https://pypi.org/project/keyring/) in your
  OS credential store. If no backend is available (common on bare Linux installs)
  it falls back to a `0600` file in your config directory **and says so** in the
  UI and activity log.
- The token needs the `repo` scope because the repo is private. A fine-grained
  token limited to a single repository works too, if you create the repo first.
- Restore paths are validated: a repo path that tries to escape its source root
  (`../../etc/passwd`) is refused rather than written.

Found a vulnerability? See [SECURITY.md](SECURITY.md).

## Limitations

Worth knowing before you rely on this:

- **Backups only run while the app is open.** There is no background service or
  autostart integration yet, see [#1](../../issues).
- **Close the game before restoring**, for the reason described above.
- **Locked files are skipped** with a warning rather than failing the backup.
  Some games hold saves open while running.
- **Files over 50 MB are skipped.** Save files are not that big; if one is,
  something has gone wrong.
- **Not a replacement for a real backup** of anything irreplaceable.

## Supported games (auto-detection)

Auto-detection knows Hollow Knight, Stardew Valley, Terraria, Minecraft (Java),
Factorio, RimWorld, The Binding of Isaac: Repentance, Dwarf Fortress, Kerbal
Space Program, Balatro, Elden Ring, Dark Souls III, Cyberpunk 2077, Baldur's
Gate 3, Valheim, Nier: Automata, Slay the Spire and Risk of Rain 2, including
Steam Proton prefixes on Linux.

**Any game works**, detection is only a shortcut. Point it at a folder and it
backs it up. Adding a preset is a one-entry change in
[`gamesync/presets.py`](gamesync/presets.py); PRs welcome.

---

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                          # run the test suite
.venv/bin/python -m pyflakes gamesync/    # lint
```

The UI tests run headless via Qt's offscreen platform:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

### Project layout

```
gamesync/
  github.py      GitHub REST client (repos + git data API)
  sync.py        backup / restore orchestration, diff-before-upload logic
  snapshot.py    reading saves off disk, exclusion rules, restore path mapping
  paths.py       portable {TOKEN} path expansion per OS
  presets.py     known save locations
  worker.py      serialised background job queue
  models.py      GameProfile / Source / AppConfig
  store.py       config persistence + keychain token storage
  ui/            Qt widgets, stylesheet, dialogs
packaging/       PyInstaller spec + AppImage build
tests/           pytest suite (sync engine against a fake GitHub, plus UI)
```

### Building distributables locally

```bash
.venv/bin/pip install -e ".[build]"
./packaging/build-appimage.sh            # Linux  → dist/GameSave-Sync-x86_64.AppImage
.venv/bin/pyinstaller packaging/gamesave-sync.spec   # any OS → dist/
```

CI builds all three platforms on every tag push. See
[`.github/workflows/release.yml`](.github/workflows/release.yml).

## Contributing

Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Adding a game
preset is the easiest place to start. Please also read the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE) © KyleIsDork

Not affiliated with GitHub, Valve, or any game developer mentioned. Game names
are trademarks of their respective owners and appear only to identify save
locations.
