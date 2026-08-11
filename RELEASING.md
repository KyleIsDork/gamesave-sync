# Releasing

Cutting a release is: bump the version, dry-run the build, tag, verify the
draft, publish.

## 1. Bump the version

Three files, and they must agree, the tag, the app's Settings screen and the
macOS bundle metadata all come from them:

| File | What to change |
|---|---|
| `gamesync/__init__.py` | `VERSION = "X.Y.Z"` |
| `pyproject.toml` | `version = "X.Y.Z"` |
| `CHANGELOG.md` | Move `[Unreleased]` entries under a new `[X.Y.Z] - YYYY-MM-DD`, and update the compare links at the bottom |

`packaging/gamesave-sync.spec` and `packaging/build-appimage.sh` both read the
version from `gamesync/__init__.py`, so they need no edit.

## 2. Check it locally

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m pyflakes gamesync/ tests/ packaging/
```

If the icon changed, regenerate the assets and commit them:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python packaging/make_icon.py
```

## 3. Dry run

Merge the version bump to `main`, then trigger the release workflow **manually**.
A manual run builds every platform and uploads the artifacts, but skips
publishing, the publish job only runs for a `v*` tag.

```bash
gh workflow run release.yml --ref main
gh run watch "$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')"
gh run download "$(gh run list --workflow=release.yml --limit 1 --json databaseId -q '.[0].databaseId')" -D /tmp/dryrun
```

Check the artifacts:

- **Linux**: launch it and confirm it stays up:
  ```bash
  chmod +x /tmp/dryrun/*.AppImage
  QT_QPA_PLATFORM=offscreen /tmp/dryrun/*.AppImage &
  sleep 15 && kill -0 $! && echo "still running" && kill $!
  ```
- **Windows**: the zip contains `GameSave Sync.exe` and an `_internal` folder.
- **macOS**: both `arm64` and `x86_64` zips exist and contain
  `GameSave Sync.app/Contents/MacOS/`.

## 4. Tag

**Tag a commit that is on `main`, not one sitting on a branch.** Tagging a
branch commit still produces a correct release, but `main` is then left
claiming the old version, and the next branch cut from it starts out wrong.

Check first:

```bash
git fetch origin
git merge-base --is-ancestor HEAD origin/main && echo "on main, safe to tag" \
  || echo "NOT on main, merge the version bump PR first"
```

Then:

```bash
git tag -a vX.Y.Z -m "GameSave Sync X.Y.Z"
git push origin vX.Y.Z
```

This rebuilds everything and opens a **draft** release with the artifacts
attached.

## 5. Check the right files

Dry-run artifacts and release assets look similar and are easy to confuse:

| Source | Filenames | Built from |
|---|---|---|
| Release assets (what ships) | `GameSave-Sync-X.Y.Z-x86_64.AppImage` | the tag |
| Dry-run artifacts | `linux-appimage.zip`, `windows-build.zip` | whatever branch you dispatched |

If a downloaded file is named `linux-appimage.zip`, it is a **dry-run artifact
wrapped by GitHub**, not a release asset, and it carries the version of the
branch it was built from. To review what will actually ship:

```bash
gh release download vX.Y.Z -D /tmp/review
ls /tmp/review    # every name should contain X.Y.Z
```

## 6. Publish

Review the draft at
[releases](https://github.com/KyleIsDork/gamesave-sync/releases), edit the notes
if needed, then publish. Publishing is deliberately manual, the workflow never
ships to users unattended.

## If something goes wrong

The release is a draft, so a broken build never reaches anyone.

```bash
git push --delete origin vX.Y.Z    # remove the tag
git tag -d vX.Y.Z                  # and locally
```

Delete the draft release on GitHub, fix the problem, and tag again.

**If the publish step fails with a 403**, the repository's default workflow
token is read-only. Fix it at *Settings → Actions → General → Workflow
permissions → Read and write*, then re-run the failed job. No re-tagging needed.

## Runner images

`release.yml` pins runner images deliberately:

- **`ubuntu-22.04`** for the AppImage, build on the oldest glibc you intend to
  support, or the result will not start on older distros.
- **`macos-15` / `macos-15-intel`**: GitHub retires macOS images regularly
  (`macos-13` is gone, `macos-14` is deprecated). If a run fails with "no runner
  matching the labels", check the current list at
  [actions/runner-images](https://github.com/actions/runner-images#available-images).
