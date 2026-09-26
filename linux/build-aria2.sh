#!/bin/sh
# Build a fully static aria2c (musl + OpenSSL) that runs on any x86_64/aarch64
# Linux distribution. Output: linux/build/aria2/aria2c
#
# Runs inside an Alpine container when Docker is available, or directly when
# already on Alpine (used by the container itself).
set -eu

ARIA2_VERSION=1.37.0
ARIA2_SHA256=60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b
ALPINE_IMAGE=alpine:3.22

HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/build/aria2"

if [ ! -f /etc/alpine-release ]; then
    command -v docker >/dev/null || { echo "docker is required to build the static aria2c" >&2; exit 1; }
    mkdir -p "$OUT"
    # ARIA2_DOCKER_ARGS: extra "docker run" arguments, e.g. proxy settings.
    # shellcheck disable=SC2086
    docker run --rm ${ARIA2_DOCKER_ARGS:-} -v "$HERE:/work" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
        "$ALPINE_IMAGE" sh /work/build-aria2.sh
    "$OUT/aria2c" --version | head -n 1
    exit 0
fi

apk add --no-cache build-base pkgconf perl linux-headers curl \
    openssl-dev openssl-libs-static zlib-dev zlib-static >/dev/null

cd /tmp
curl -fsSL -o aria2.tar.xz \
    "https://github.com/aria2/aria2/releases/download/release-$ARIA2_VERSION/aria2-$ARIA2_VERSION.tar.xz"
echo "$ARIA2_SHA256  aria2.tar.xz" | sha256sum -c -
tar xf aria2.tar.xz
cd "aria2-$ARIA2_VERSION"

# aria2 aborts at startup when OpenSSL 3's "legacy" provider cannot be loaded.
# That provider is a separate plugin file a static binary cannot load, and it
# only supplies RC4 for BitTorrent encryption, which this build leaves out.
sed -i 's/throw DL_ABORT_EX("OSSL_PROVIDER_load .legacy. failed.");/;/' src/Platform.cc
grep -q "OSSL_PROVIDER_load 'legacy' failed" src/Platform.cc && { echo "Platform.cc patch failed" >&2; exit 1; }

# HTTP(S) only: the features we do not use (BitTorrent, Metalink, SFTP, cookie
# databases) are left out to keep the binary small and dependency free.
./configure --prefix=/usr --disable-nls --disable-bittorrent --disable-metalink \
    --with-openssl --without-gnutls --without-libssh2 --without-sqlite3 \
    --without-libxml2 --without-libexpat --without-libcares --without-libgmp \
    --without-libnettle --without-libgcrypt \
    ARIA2_STATIC=yes LDFLAGS="-static" >/dev/null
make -j"$(nproc)" >/dev/null
strip src/aria2c

mkdir -p /work/build/aria2
cp src/aria2c /work/build/aria2/aria2c
cp COPYING /work/build/aria2/COPYING
if [ -n "${HOST_UID:-}" ]; then
    chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" /work/build
fi
file_info=$(ldd src/aria2c 2>&1 || true)
echo "aria2c built: $(src/aria2c --version | head -n 1) ($file_info)"
