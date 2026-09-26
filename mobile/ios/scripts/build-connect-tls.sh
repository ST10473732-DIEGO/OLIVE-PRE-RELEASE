#!/bin/bash
# Reproducible local dependency, never downloads during an Xcode build.
set -euo pipefail
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=3.5.8
SHA=a8f84a39918ec6415ce765d9b429d313ba97b8143169c172e734b9514464f5b2
ARCHIVE="${OLIVE_OPENSSL_ARCHIVE:-/tmp/olive-openssl-$VERSION.tar.gz}"
if [ ! -f "$ARCHIVE" ]; then
  curl -fL "https://www.openssl.org/source/openssl-$VERSION.tar.gz" -o "$ARCHIVE"
fi
printf '%s  %s\n' "$SHA" "$ARCHIVE" | shasum -a 256 -c -
WORK="$(mktemp -d /tmp/olive-tls-build.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
for SLICE in iphoneos-arm64 iphonesimulator-arm64 iphonesimulator-x86_64; do
  SDK="${SLICE%-*}"
  ARCH="${SLICE##*-}"
  DEST="$ROOT/Vendor/OpenSSL/$SDK/$ARCH"
  mkdir -p "$WORK/$SLICE" "$DEST"
  tar -xzf "$ARCHIVE" -C "$WORK/$SLICE" --strip-components=1
  (
    cd "$WORK/$SLICE"
    SYSROOT="$(xcrun --sdk "$SDK" --show-sdk-path)"
    TARGET="$ARCH-apple-ios17.0"
    if [ "$SDK" = iphonesimulator ]; then TARGET="$TARGET-simulator"; fi
    CONFIG=ios64-cross
    if [ "$ARCH" = x86_64 ]; then CONFIG=iossimulator-xcrun; fi
    CC="$(xcrun --sdk "$SDK" -f clang)" CFLAGS="-target $TARGET -isysroot $SYSROOT" ./Configure "$CONFIG" no-shared no-tests no-apps no-module no-dso no-engine no-legacy no-ui-console no-autoload-config no-asm \
      --prefix="$DEST" --openssldir="$DEST/ssl"
    make -j "${OLIVE_BUILD_JOBS:-6}" build_libs
    make install_dev
  )
done
cp "$WORK/iphoneos-arm64/LICENSE.txt" "$ROOT/Vendor/OpenSSL/LICENSE.txt"
