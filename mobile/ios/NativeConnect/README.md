# Connect TLS adapter

This is an in-process native TLS implementation, not a translation service.
`OliveTLS.c` deliberately exposes no socket, file, system-root, diagnostic-text,
or private-key export API. Swift owns lifecycle and bounded transport. The
adapter matches `olive/connect/tls_identity.py` using TLS 1.3, Ed25519 X.509,
self-signed exact peer pins, current validity, mutual client authentication,
no session cache/tickets, and the exact C2 exporter label/context.

C4.1 carries memory-BIO TLS records inside a four-byte network-order length
prefix; C3 uses the same identity on an ordinary TLS stream with six-byte
application headers. A standard `NWConnection` TLS stream is not a drop-in
replacement for both carriers. Apple Network.framework still owns Bonjour,
Wi-Fi routing, TCP, local-network privacy and connection lifecycle. No ATS
exception is needed or present. Apple CryptoKit handles Ed25519 seed generation
and receipt signing; Keychain protects the identity envelope at rest.

Build the pinned upstream **OpenSSL 3.5.8** source locally:

```sh
bash mobile/ios/scripts/build-connect-tls.sh
```

Source: <https://www.openssl.org/source/openssl-3.5.8.tar.gz>

SHA-256: `a8f84a39918ec6415ce765d9b429d313ba97b8143169c172e734b9514464f5b2`.
The build script checks this digest before extracting. `OLIVE_OPENSSL_ARCHIVE`
may point at an already-downloaded archive. No Xcode build downloads code.
Device arm64 and simulator arm64/x86_64 are built for iOS 17. Binaries stay in
ignored `Vendor/OpenSSL`; no machine-specific path or binary is committed.
The upstream Apache 2.0 license is retained and bundled with the application.
Updating this dependency requires a new checksum and interop/security rerun.

Secure Enclave is not used: Connect's signing identity is Ed25519, while the
app's iOS 17 Secure Enclave API supplies P-256. Changing the curve would change
Connect's trust model. Raw seeds remain in an app-scoped, nonsynchronizing,
WhenUnlockedThisDeviceOnly Keychain item, never preferences or a PEM file.

For reproducible Mac cross-language tests:

```sh
OLIVE_PYTHON=/path/to/project/python bash mobile/ios/scripts/check-connect-interop.sh
```

Set `OLIVE_HOST_OPENSSL` if development headers/libs are elsewhere. The host
harness uses that installed OpenSSL build; iPhone tests use the pinned iOS
build. Host fixture pipes are protocol tests and never stand in for real LAN
acceptance. The fixture executable is not part of the iOS app target.
