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
  mobile/ios/OLIVEMobile/Core/Connect/RemoteChatClient.swift \
  mobile/ios/OLIVEMobile/Core/Chat/ChatMediaStore.swift \
  mobile/ios/OLIVEMobile/Core/Connect/ConnectIdentityStore.swift \
  mobile/ios/OLIVEMobile/Core/Connect/ConnectTLS.swift \
  mobile/ios/OLIVEMobile/Core/Security/SecretStore.swift \
  mobile/ios/OLIVEMobile/Core/Notes/NotesDatabase.swift \
  mobile/ios/OLIVEMobile/Core/Notes/NotesEngineHost.swift \
  $(ls mobile/ios/OLIVEMobile/Core/Draw/*.swift | grep -v DrawSync.swift) mobile/ios/Interop/DrawHarness.swift \
  mobile/ios/Interop/ChatHarness.swift \
  mobile/ios/Interop/main.swift "$OUT/tls.o" \
  -L"$OPENSSL/lib" -lssl -lcrypto -o "$OUT/interop"
"$OUT/interop" tests/fixtures/mobile_connect/vectors.json "$OUT/swift.json"
"$PYTHON" scripts/mobile_connect_vectors.py --swift-output "$OUT/swift.json"

OLIVE_SWIFT_INTEROP="$OUT/interop" "$PYTHON" -m unittest tests.test_mobile_pairing_interop -v

"$OUT/interop" --companion-fixture tests/fixtures/mobile_connect/companion.json "$OUT/companion.json"
"$PYTHON" scripts/mobile_companion_vectors.py --swift-output "$OUT/companion.json"

"$OUT/interop" --calendar-fixture tests/fixtures/mobile_connect/calendar.json

# OLIVE Notes: the committed phone engine in the real Swift JavaScriptCore host
# and SQLite store, against the Python desktop engine (olive-notes/1 bytes).
OLIVE_NOTES_SWIFT_HARNESS="$OUT/interop" "$PYTHON" -m unittest tests.test_notes_phone_engine -v

# OLIVE Draw: the phone's native Swift engine (SQLite store, replica rules,
# olive-draw/1 codec, image canonicalization, CoreGraphics renderer) against the
# Python desktop engine over real olive-draw/1 bytes.
OLIVE_DRAW_SWIFT_HARNESS="$OUT/interop" "$PYTHON" -m unittest tests.test_draw_phone_engine -v

# Remote Chat v2 (olive-chat/1): the phone's RemoteChatClient, ChatWire and
# ChatMediaStore against the Python RemoteChatService over real packet bytes.
OLIVE_CHAT_SWIFT_HARNESS="$OUT/interop" "$PYTHON" -m unittest tests.test_mobile_chat_interop -v
