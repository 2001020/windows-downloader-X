#!/usr/bin/env bash
# Build WinISO Downloader for macOS.
#
# Output (in macos/dist/):
#   WinISO-Downloader-macOS.dmg   drag "WinISO Downloader.app" to Applications
#   WinISO-Downloader-macOS.zip   the same app bundle, zipped
#
# Use the python.org installer's Python (universal2) to get an app that runs
# natively on both Apple Silicon and Intel Macs; any other Python produces an
# app for its own architecture only.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
PYTHON=${PYTHON:-python3}
NAME="WinISO Downloader"
BUILD="$HERE/build"
DIST="$HERE/dist"
VERSION=$(PYTHONPATH="$ROOT/common" "$PYTHON" -c "import winiso; print(winiso.__version__)")

cd "$HERE"

if [ ! -x "$BUILD/aria2/aria2c" ]; then
    bash "$HERE/build-aria2.sh"
fi

if [ -z "${SKIP_PIP:-}" ]; then
    "$PYTHON" -m pip install -r "$ROOT/common/requirements-build.txt"
fi

TARGET_ARCH=()
PY_EXE=$("$PYTHON" -c "import sys; print(sys.executable)")
if lipo -archs "$(readlink -f "$PY_EXE" 2>/dev/null || echo "$PY_EXE")" 2>/dev/null | grep -q "x86_64.*arm64\|arm64.*x86_64"; then
    TARGET_ARCH=(--target-arch universal2)
    echo "Building a universal2 app"
fi

rm -rf "$BUILD/pyinstaller" "$BUILD/work"
"$PYTHON" -m PyInstaller --noconfirm --clean --windowed --onedir --name "$NAME" \
    ${TARGET_ARCH[@]+"${TARGET_ARCH[@]}"} \
    --icon "$HERE/icon.icns" \
    --osx-bundle-identifier io.github.winiso-downloader \
    --paths "$ROOT/common" \
    --add-binary "$BUILD/aria2/aria2c:aria2" \
    --add-data "$ROOT/common/winiso/assets:assets" \
    --collect-data sv_ttk \
    --distpath "$BUILD/pyinstaller" --workpath "$BUILD/work" --specpath "$BUILD" \
    "$HERE/main.py"

APPDIR="$BUILD/pyinstaller/$NAME.app"
PLIST="$APPDIR/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace CFBundleDisplayName -string "$NAME" "$PLIST"
plutil -replace LSMinimumSystemVersion -string "10.13" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"
plutil -replace NSHumanReadableCopyright -string "aria2 is GPL-2.0-or-later; Windows is a trademark of Microsoft" "$PLIST"
# Editing Info.plist invalidates PyInstaller's ad-hoc signature; sign again
# (Apple Silicon refuses to run unsigned code).
codesign --force --deep --sign - "$APPDIR"
codesign --verify --deep --strict "$APPDIR"

mkdir -p "$DIST"
rm -f "$DIST/WinISO-Downloader-macOS.dmg" "$DIST/WinISO-Downloader-macOS.zip"
ditto -c -k --sequesterRsrc --keepParent "$APPDIR" "$DIST/WinISO-Downloader-macOS.zip"

STAGE="$BUILD/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APPDIR" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$HERE/README.md" "$STAGE/README.md"
hdiutil create -volname "$NAME" -srcfolder "$STAGE" -ov -format UDZO "$DIST/WinISO-Downloader-macOS.dmg"

echo
echo "Built:"
ls -lh "$DIST"
