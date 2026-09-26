# OLIVE for iPhone — C9.1

Native SwiftUI companion shell. Home, Chat drafts, Devices and Settings work
locally. Pairing and remote answers are not implemented. No Python runtime,
cloud service or Swift package dependency is embedded.

Open `OLIVEMobile.xcodeproj`; select the shared **OLIVEMobile** scheme.
The app supports iPhone on **iOS 17+**, in portrait and landscape.
All three targets use Swift 6. The product name on the phone is **OLIVE**.

## Build and test

Run from the repository root. Select your installed Xcode for this shell only:

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
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
use a separate debug-only namespace. Screenshots are attachments of OLIVE's
window; never capture unrelated device contents for acceptance evidence.

## Source layout

- `App`: composition root and main-actor Observation state.
- `Navigation`: three native tabs and a Settings sheet.
- `Features`: small Home, Chat, Devices and Settings views.
- `DesignSystem`: Grove semantic colors, type, spacing and components.
- `Core/Models`: local presentation values, not desktop database replicas.
- `Core/Persistence`: versioned, protected local draft file; navigation defaults.
- `Core/Connect`: disconnected domain interfaces; no network or JSON codecs.
- `Core/Security`: injectable Keychain boundary; production creates no secrets.
- `OLIVEMobileTests`, `OLIVEMobileUITests`: state, persistence, Keychain and UI checks.

The app uses the repository's canonical olive mark. Recreate its opaque icon:

```sh
swift mobile/ios/scripts/render-icon.swift assets/branding/olive-source.png \
  mobile/ios/OLIVEMobile/Assets.xcassets/AppIcon.appiconset/AppIcon.png
```

See [the foundation report](../../../docs/OLIVE_MOBILE_C9_1_FOUNDATION.md) for protocol
sources, acceptance evidence, design choices and C9.2 requirements.
