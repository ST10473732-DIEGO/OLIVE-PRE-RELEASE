# OLIVE for iPhone

The iPhone app is a native SwiftUI companion. It pairs with your OLIVE computer
and sends requests to it; the computer runs the models and returns the results.
It offers every desktop Chat mode, attachments, Notes, Draw, Today, Files and
Remote Studio, on the home network (Direct) or away from home through Connect World.

## Installing

Today the app is installed by building it with Xcode on a Mac. Build, signing and
test instructions are in [`mobile/ios/README.md`](../../mobile/ios/README.md):
build the bundled OpenSSL once, choose your signing team locally, then run on a
physical iPhone (iOS 17 or later; continued background work needs iOS 26).

TestFlight and App Store distribution, the final bundle ID and version 1.0.0 are
planned for a dedicated iOS release phase. Changing the bundle ID changes where the
phone keeps its pairing identity, so it will be done once, deliberately.

## Pairing and permissions

- [Pairing](../connect/pairing.md) and [Devices](../connect/devices.md): pairing
  proves which device is which; it grants no capability by itself.
- Each capability (Remote AI, sync, files, Studio) is Off, Ask or Allow per device.
- Away from home: [Connect World](../connect-world/README.md). Provision the phone
  on the home network first.

## Protocols

[`olive-chat/1`](../connect/protocol/olive-chat-1.md) (Chat),
[Notes](../features/notes.md) (`olive-notes/1`), [Draw](../features/draw.md)
(`olive-draw/1`), and the [Connect protocol family](../connect/README.md).
