# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Restores can upload themselves. "Make this the newest backup on GitHub", on by
  default in the History dialog, commits the restored files right after they are
  written to disk. Without it a rollback only existed on one machine until its
  next scheduled backup, and any other machine could push the save you had just
  rolled back from. The commit records what it came from,
  `<game>: restored backup <sha>`.

### Changed

- The pre-restore zip of your current files is no longer optional. The checkbox
  offering to skip it is gone, because the case for skipping it was thin and the
  cost of skipping it is an unrecoverable save.

### Fixed

- A pre-restore zip that could not be written was silently ignored, and the
  restore then overwrote the save files with no copy of them kept anywhere. A
  failed safety copy now aborts the restore before anything is written.

## [0.1.1] - 2026-08-11

### Added

- Background operation: a system tray icon with open, back up now, pause and
  quit. Closing the window now hides to the tray and backups keep running.
  Sessions with no tray fall back to closing meaning quit.
- Start at login, on all three platforms, via an XDG autostart entry, a
  LaunchAgent, or the Windows Run key. Started this way the app comes up hidden
  with `--background`.
- Steam library discovery by reading `steamapps/libraryfolders.vdf` and
  `appmanifest_*.acf`. Games installed to a library on a second drive are now
  found, where previously only a default install path was guessed.
- Parameterised path tokens `{STEAM_COMPAT:<appid>}` and `{STEAM_APP:<appid>}`,
  which resolve through Steam rather than a fixed root. A Proton game's save
  path is now portable between machines that keep their libraries in different
  places.
- WEBFISHING preset, both native and through Proton.

### Fixed

- Buttons that open a browser or file manager failed silently. The return value
  of `QDesktopServices.openUrl` was ignored, so "Open repo on GitHub", the token
  page link, and "Open folder" could do nothing at all with no feedback. They now
  fall back to the platform launcher and then to `webbrowser`, and report the
  address if every method fails.
- The AppImage `AppRun` exported `LD_LIBRARY_PATH` and `QT_PLUGIN_PATH` pointing
  at a `usr/lib` directory that does not exist in the AppDir. Besides being
  useless, exporting them leaked the bundle's loader paths into any program the
  app launched.

## [0.1.0] - 2026-08-11

First release.

### Added

- Desktop GUI (PySide6) with dark and light themes, sidebar navigation, per-game
  cards, activity log and settings.
- GitHub connection flow: personal access token, stored in the OS keychain via
  `keyring`, with a documented `0600` file fallback when no backend exists.
- Automatic creation of a **private** saves repository on the user's account.
- Per-game backup profiles: multiple file/folder sources, glob exclusions, and
  schedules from every 5 minutes to daily.
- Scheduled and manual backups, committed through the GitHub git data API, no
  local clone and no `git` binary required.
- Incremental uploads: git blob SHAs are computed locally and diffed against the
  remote tree, so unchanged saves upload nothing and create no commit.
- Deletion propagation: files removed on disk are removed from the tree in the
  same commit.
- Backup history browser and restore of any previous commit, with the current
  files zipped to a pre-restore folder first.
- Auto-detection of save locations for 18 games across Windows, macOS and Linux,
  including Steam Proton prefixes.
- Portable `{TOKEN}` path storage so profiles resolve across machines and OSes.
- Retry on a losing ref race when another machine commits concurrently.
- Restore path validation rejecting paths that escape their source root.
- Failure backoff so a repeatedly failing game does not hammer the API.

[Unreleased]: https://github.com/KyleIsDork/gamesave-sync/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/KyleIsDork/gamesave-sync/releases/tag/v0.1.1
[0.1.0]: https://github.com/KyleIsDork/gamesave-sync/releases/tag/v0.1.0
