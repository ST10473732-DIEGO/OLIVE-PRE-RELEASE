# OLIVE for iPhone — C9.3 companion

Native SwiftUI Connect client, preserving the C9.1 Home, Chat, Devices and
Settings foundation. C9.2 implements Bonjour discovery, Keychain identity,
existing C2/C4 pairing, C3 transport and C7 incremental remote Chat with Stop.
C9.2 real-device pairing/Chat acceptance is complete. C9.3 adds Home links to
Today/agenda, selected Chat, C6 Files and C8 Remote Studio, with protected local
stores and Apple continued-processing support for user-started work on iOS 26+.
Real C9.3 acceptance remains partial; see the evidence report before sign-off.
No Python runtime or cloud service is embedded.

**OLIVE Notes** (tab *Notes*) is a local-first notepad that syncs with the
paired computer over Connect frames 13/14 (`olive-notes/1`). Its engine is
`OLIVEMobile/Resources/NotesEngine.js`, generated from
`desktop/src/features/notes/engine/` by `node desktop/scripts/build-notes-engine.mjs`
(do not edit the bundle by hand), run in JavaScriptCore with a SQLite store.
See `docs/OLIVE_NOTES.md`. The Notes Swift code was written on Linux and still
needs its first Xcode build, unit tests and interop run here.

Open `OLIVEMobile.xcodeproj`; select the shared **OLIVEMobile** scheme.
The app supports iPhone on **iOS 17+**, in portrait and landscape.
All three targets use Swift 6. The product name on the phone is **OLIVE**.

## Build and test

Run from the repository root. Select your installed Xcode for this shell only:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
bash mobile/ios/scripts/build-connect-tls.sh
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -list
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile -showBuildSettings
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile -showdestinations
xcrun simctl list devices available
xcrun devicectl list devices
```

Build the app and both test bundles without a signing account:

```sh
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/olive-ios-simulator CODE_SIGNING_ALLOWED=NO build-for-testing
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile \
  -destination 'generic/platform=iOS' \
  -derivedDataPath /tmp/olive-ios-generic CODE_SIGNING_ALLOWED=NO build
```

For runtime tests, substitute a simulator UUID from `simctl` (an installed iOS
runtime is required):

```sh
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile \
  -destination "platform=iOS Simulator,id=$OLIVE_SIMULATOR_ID" \
  -derivedDataPath /tmp/olive-ios-simulator \
  -resultBundlePath /tmp/olive-simulator-tests.xcresult \
  -parallel-testing-enabled NO test
```

Signing team and device IDs intentionally remain local. In Xcode select your
Apple Team under Signing & Capabilities, or supply it on the command line:

```sh
xcodebuild -project mobile/ios/OLIVEMobile.xcodeproj -scheme OLIVEMobile \
  -destination "platform=iOS,id=$OLIVE_IPHONE_ID" \
  -derivedDataPath /tmp/olive-ios-device DEVELOPMENT_TEAM="$OLIVE_APPLE_TEAM" \
  -allowProvisioningUpdates -allowProvisioningDeviceRegistration \
  -resultBundlePath /tmp/olive-iphone-tests.xcresult \
  -parallel-testing-enabled NO test
xcrun devicectl device install app --device "$OLIVE_IPHONE_ID" \
  /tmp/olive-ios-device/Build/Products/Debug-iphoneos/OLIVEMobile.app
xcrun devicectl device process launch --device "$OLIVE_IPHONE_ID" \
  io.github.st10473732-diego.olive.mobile
```

Use a new result-bundle path for each run. Physical tests operate only inside
OLIVE, apart from briefly backgrounding it and rotating the device. Test drafts
use a separate debug-only namespace. Screenshots are captured only after confirming OLIVE is foreground, including
its keyboard. Never capture unrelated device contents for acceptance evidence.

The explicit real-LAN discovery test is skipped by default. With the real desktop
already advertising Connect, prefix the physical `xcodebuild test` command with
`TEST_RUNNER_OLIVE_C92_LAN_ACCEPTANCE=1`. It opens the normal app and checks for an
actual Bonjour result; it does not approve pairing or grant any capability.
Pairing, permission, real model execution, Stop and reconnect require the
separate real-device acceptance sequence in the C9.2 report.

Cross-language fixture checks use the project Python environment and a host
OpenSSL development installation:

```sh
OLIVE_PYTHON=/path/to/project/python bash mobile/ios/scripts/check-connect-interop.sh
python -m unittest tests.test_mobile_connect_vectors tests.test_mobile_connect_tls -v
```

The [native adapter guide](NativeConnect/README.md) records the pinned source,
checksum, license and dependency build. Downloading/building it is an explicit
development step; Xcode does not fetch dependencies.

## Source layout

- `App`: composition root and main-actor Observation state.
- `Navigation`: three native tabs and a Settings sheet.
- `Features`: Home, Chat/selected Chat, Today/agenda, Files, Studio, Devices and Settings.
- `DesignSystem`: Grove semantic colors, type, spacing and components.
- `Core/Models`: local presentation values, not desktop database replicas.
- `Core/Persistence`: atomic protected stores and explicit preserved-data recovery; keys stay in Keychain.
- `Core/Background`: user-initiated continued processing, operation journal and opt-in completion notifications.
- `Core/Connect`: discovery, identity, pairing, trust, transport, session and C7 client.
- `Core/Connect/Wire`: canonical C2/C3/C5/C6/C7/C8 mappings and bounded calendar recurrence.
- `Core/Security`: injectable, device-only Keychain boundary.
- `NativeConnect`: in-process Ed25519 X.509 and TLS memory-BIO adapter.
- `OLIVEMobileTests`, `OLIVEMobileUITests`: state, persistence, Keychain and UI checks.

The app uses the repository's canonical olive mark. Recreate its opaque icon:

```sh
swift mobile/ios/scripts/render-icon.swift assets/branding/olive-source.png \
  mobile/ios/OLIVEMobile/Assets.xcassets/AppIcon.appiconset/AppIcon.png
```

See [the unchanged C9.1 foundation report](../../../docs/OLIVE_MOBILE_C9_1_FOUNDATION.md)
and [C9.2 protocol mapping and acceptance](../../../docs/OLIVE_MOBILE_C9_2_CONNECT_CHAT.md).


See [C9.3 implementation and acceptance](../../../docs/OLIVE_MOBILE_C9_3_FEATURES_BACKGROUND.md)
for background/force-quit semantics, the 64 MiB C6 limit, Swift/Python fixtures,
explicit Sync/retry behavior and the remaining real CachyOS acceptance matrix.
`check-connect-interop.sh` also checks canonical calendar validation/occurrences
against `scripts/mobile_calendar_vectors.py`, using the desktop production code.
Debug-only UI fixtures run under a separate `--ui-test-session` directory; they
cannot establish a connection or confer desktop authority.
