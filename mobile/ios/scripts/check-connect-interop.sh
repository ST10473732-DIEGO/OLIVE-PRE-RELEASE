#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export OLIVE_DATA_DIR="${OLIVE_DATA_DIR:-/tmp/olive-mobile-interop-profile}"
PYTHON="${OLIVE_PYTHON:-python3}"
OPENSSL="${OLIVE_HOST_OPENSSL:-/opt/homebrew/opt/openssl@3}"
OUT="$(mktemp -d /tmp/olive-interop.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT
xcrun clang -I"$OPENSSL/include" -c mobile/ios/NativeConnect/OliveTLS.c -o "$OUT/tls.o"
xcrun swiftc -swift-version 6 -module-cache-path "$OUT/cache" \
  -import-objc-header mobile/ios/NativeConnect/OliveTLS.h \
  mobile/ios/OLIVEMobile/Core/Connect/Wire/*.swift \
  mobile/ios/OLIVEMobile/Core/Connect/ConnectFailure.swift \
  mobile/ios/OLIVEMobile/Core/Connect/ConnectIdentityStore.swift \
  mobile/ios/OLIVEMobile/Core/Connect/ConnectTLS.swift \
  mobile/ios/OLIVEMobile/Core/Security/SecretStore.swift \
  mobile/ios/Interop/main.swift "$OUT/tls.o" \
  -L"$OPENSSL/lib" -lssl -lcrypto -o "$OUT/interop"
"$OUT/interop" tests/fixtures/mobile_connect/vectors.json "$OUT/swift.json"
"$PYTHON" scripts/mobile_connect_vectors.py --swift-output "$OUT/swift.json"

OLIVE_SWIFT_INTEROP="$OUT/interop" "$PYTHON" -m unittest tests.test_mobile_pairing_interop -v

"$OUT/interop" --companion-fixture tests/fixtures/mobile_connect/companion.json "$OUT/companion.json"
"$PYTHON" scripts/mobile_companion_vectors.py --swift-output "$OUT/companion.json"

"$OUT/interop" --calendar-fixture tests/fixtures/mobile_connect/calendar.json
