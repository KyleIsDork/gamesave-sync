#!/usr/bin/env bash
# Build a Linux AppImage.
#
#   ./packaging/build-appimage.sh
#
# Output: dist/GameSave-Sync-x86_64.AppImage
#
# Build on the OLDEST glibc you intend to support, an AppImage built on a new
# distro will not run on older ones. CI uses ubuntu-22.04 for this reason.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c 'import re,pathlib; print(re.search(r"VERSION = \"([^\"]+)\"", pathlib.Path("gamesync/__init__.py").read_text()).group(1))')"
ARCH="${ARCH:-x86_64}"
APPDIR="$ROOT/build/AppDir"

echo "==> Building GameSave Sync $VERSION for $ARCH"

echo "==> Running PyInstaller"
rm -rf "$APPDIR" dist/gamesave-sync
python3 -m PyInstaller --noconfirm --clean packaging/gamesave-sync.spec

echo "==> Assembling AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a dist/gamesave-sync/. "$APPDIR/usr/bin/"

# The AppImage spec wants the desktop file and icon at the AppDir root as well
# as in the usual share/ locations.
cp packaging/appimage/gamesave-sync.desktop "$APPDIR/gamesave-sync.desktop"
cp packaging/appimage/gamesave-sync.desktop "$APPDIR/usr/share/applications/"
cp assets/icon-256.png "$APPDIR/gamesave-sync.png"
cp assets/icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/gamesave-sync.png"
cp packaging/appimage/AppRun "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"

echo "==> Fetching appimagetool"
TOOL="build/appimagetool-${ARCH}.AppImage"
if [ ! -f "$TOOL" ]; then
    mkdir -p build
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$TOOL"
fi

echo "==> Packaging"
mkdir -p dist
OUT="dist/GameSave-Sync-${VERSION}-${ARCH}.AppImage"

# appimagetool needs FUSE; --appimage-extract-and-run avoids needing it in
# containers and CI runners where /dev/fuse is unavailable.
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"

chmod +x "$OUT"
echo "==> Done: $OUT"
ls -lh "$OUT"
