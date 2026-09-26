#!/usr/bin/env bash
# Build a universal (arm64 + x86_64) aria2c for macOS that depends only on
# system frameworks (AppleTLS for HTTPS). Output: macos/build/aria2/aria2c
set -euo pipefail

ARIA2_VERSION=1.37.0
ARIA2_SHA256=60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b
export MACOSX_DEPLOYMENT_TARGET=10.13

HERE=$(cd "$(dirname "$0")" && pwd)
WORK="$HERE/build/aria2-src"
OUT="$HERE/build/aria2"

mkdir -p "$WORK" "$OUT"
cd "$WORK"
if [ ! -f aria2.tar.xz ]; then
    curl -fsSL -o aria2.tar.xz \
        "https://github.com/aria2/aria2/releases/download/release-$ARIA2_VERSION/aria2-$ARIA2_VERSION.tar.xz"
fi
echo "$ARIA2_SHA256  aria2.tar.xz" | shasum -a 256 -c -

for arch in arm64 x86_64; do
    rm -rf "$arch"
    mkdir "$arch"
    tar -xf aria2.tar.xz -C "$arch" --strip-components 1
    (
        cd "$arch"
        # HTTP(S) only; everything else is disabled so nothing from Homebrew is
        # picked up and the binary needs only macOS system libraries.
        ./configure --host="$arch-apple-darwin" \
            CC="clang -arch $arch" CXX="clang++ -arch $arch" \
            CFLAGS="-O2 -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
            CXXFLAGS="-O2 -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
            LDFLAGS="-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
            PKG_CONFIG_PATH=/nonexistent PKG_CONFIG_LIBDIR=/nonexistent \
            --disable-nls --disable-bittorrent --disable-metalink \
            --with-appletls --without-openssl --without-gnutls --without-libssh2 \
            --without-sqlite3 --without-libxml2 --without-libexpat --without-libcares \
            --without-libz --without-libgmp --without-libnettle --without-libgcrypt \
            >configure.log
        make -j"$(sysctl -n hw.ncpu)" >make.log
        strip src/aria2c
    )
done

lipo -create -output "$OUT/aria2c" arm64/src/aria2c x86_64/src/aria2c
cp arm64/COPYING "$OUT/COPYING"
lipo -info "$OUT/aria2c"
otool -L "$OUT/aria2c"
"$OUT/aria2c" --version | head -n 1
