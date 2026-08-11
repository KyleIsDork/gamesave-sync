# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Scheduled and manual backups, committed through the GitHub git data API — no
  local clone and no `git` binary required.
- Incremental uploads: git blob SHAs are computed locally and diffed against the
  remote tree, so unchanged saves upload nothing and create no commit.
- Deletion propagation — files removed on disk are removed from the tree in the
  same commit.
- Backup history browser and restore of any previous commit, with the current
  files zipped to a pre-restore folder first.
- Auto-detection of save locations for 18 games across Windows, macOS and Linux,
  including Steam Proton prefixes.
- Portable `{TOKEN}` path storage so profiles resolve across machines and OSes.
- Retry on a losing ref race when another machine commits concurrently.
- Restore path validation rejecting paths that escape their source root.
- Failure backoff so a repeatedly failing game does not hammer the API.

[Unreleased]: https://github.com/KyleIsDork/gamesave-sync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/KyleIsDork/gamesave-sync/releases/tag/v0.1.0
