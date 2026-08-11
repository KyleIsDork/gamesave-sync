# Security Policy

## Supported versions

The latest release is supported. This is a small project — fixes go into the
next release rather than being backported.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately via GitHub's
[private vulnerability reporting](https://github.com/KyleIsDork/gamesave-sync/security/advisories/new)
(Security tab → Report a vulnerability).

Include what you can: affected version, OS, reproduction steps, and impact.
Expect an initial response within about a week — this is maintained in spare
time, not by a security team.

## Scope

This app handles a GitHub personal access token and writes files to disk, so the
interesting areas are:

- **Token handling.** The token is stored via `keyring` in the OS credential
  store, or in a `0600` file in the user's config directory when no keyring
  backend exists. It is sent only to `api.github.com` over HTTPS, and is never
  written to the activity log or committed to the saves repo.
- **Restore path handling.** Restore writes files to disk based on paths that
  come from the repository. Paths are validated against their source root and
  anything that escapes it is refused. Reports of a bypass are very welcome.
- **The saves repository is created private.** A path that could cause it to be
  created or made public is a valid report.

## Out of scope

- The GitHub token having broad `repo` scope. That is a documented consequence
  of the repo being private; use a fine-grained token if you want it narrower.
- Anyone with access to your unlocked user session being able to read your
  config or trigger a backup. The app has the same privileges you do.
- Unsigned macOS and Windows builds. Known, documented in the README, and
  tracked as future work.
