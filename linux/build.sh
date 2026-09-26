#!/usr/bin/env bash
# Build WinISO Downloader for Linux.
#
# Output (in linux/dist/):
#   WinISO-Downloader-<arch>.AppImage          double-click to run
#   WinISO-Downloader-linux-<arch>.tar.gz      same AppImage, keeps the executable bit
#
# Requirements: Python 3.9+ with Tk (e.g. apt install python3-tk), Docker for the
# static aria2c (or put an aria2c binary at linux/build/aria2/aria2c first).
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
PYTHON=${PYTHON:-python3}
ARCH=$(uname -m)
APP=winiso-downloader
BUILD="$HERE/build"
DIST="$HERE/dist"
APPDIR="$BUILD/AppDir"

cd "$HERE"

if [ ! -x "$BUILD/aria2/aria2c" ]; then
    sh "$HERE/build-aria2.sh"
fi

if [ -z "${SKIP_PIP:-}" ]; then
    "$PYTHON" -m pip install -r "$ROOT/common/requirements-build.txt"
fi

rm -rf "$BUILD/pyinstaller" "$BUILD/work" "$APPDIR"
"$PYTHON" -m PyInstaller --noconfirm --clean --onedir --name "$APP" \
    --paths "$ROOT/common" \
    --add-binary "$BUILD/aria2/aria2c:aria2" \
    --add-data "$ROOT/common/winiso/assets:assets" \
    --distpath "$BUILD/pyinstaller" --workpath "$BUILD/work" --specpath "$BUILD" \
    "$HERE/main.py"

# Libraries every desktop already has and that must match the system's own
# configuration (fonts, X server). Bundling them causes font and display bugs.
# Same idea as the AppImage project's excludelist.
for lib in libfontconfig.so libfreetype.so libX11.so libX11-xcb.so libxcb.so libexpat.so; do
    find "$BUILD/pyinstaller/$APP" -name "$lib.*" -delete
done

# AppDir layout
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$BUILD/pyinstaller/$APP" "$APPDIR/usr/lib/$APP"
install -m 755 "$HERE/AppRun" "$APPDIR/AppRun"
install -m 644 "$HERE/$APP.desktop" "$APPDIR/$APP.desktop"
install -m 644 "$HERE/$APP.desktop" "$APPDIR/usr/share/applications/$APP.desktop"
install -m 644 "$HERE/$APP.png" "$APPDIR/$APP.png"
install -m 644 "$HERE/$APP.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP.png"
ln -sf "$APP.png" "$APPDIR/.DirIcon"

# appimagetool
TOOL="$BUILD/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$DIST"
OUT="$DIST/WinISO-Downloader-$ARCH.AppImage"
rm -f "$OUT"
# Extract-and-run: works without FUSE (CI containers, Docker).
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=$ARCH "$TOOL" --no-appstream "$APPDIR" "$OUT"
chmod +x "$OUT"

# The tarball preserves the executable bit, which browsers drop on download.
PKG="$BUILD/WinISO-Downloader-linux-$ARCH"
rm -rf "$PKG"
mkdir -p "$PKG"
cp "$OUT" "$PKG/"
cp "$HERE/README.md" "$PKG/README.md"
tar -C "$BUILD" -czf "$DIST/WinISO-Downloader-linux-$ARCH.tar.gz" "WinISO-Downloader-linux-$ARCH"

echo
echo "Built:"
ls -lh "$DIST"
