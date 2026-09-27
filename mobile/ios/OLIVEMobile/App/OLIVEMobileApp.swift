import SwiftUI

@main
struct OLIVEMobileApp: App {
    @State private var state: AppState
    init() {
        // UI tests use an isolated preferences domain and protected draft folder.
        // This contains no synthetic peer, message or connected backend state.
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if ProcessInfo.processInfo.environment["OLIVE_C92_CANCEL_ACCEPTANCE"] == "1" {
            // The XCTest owns the one real channel; the shell must not create a
            // competing session that would interrupt its cancellation probes.
            let directory = URL.applicationSupportDirectory.appendingPathComponent("C92TransportTests")
            _state = State(initialValue: AppState(store: LocalShellStore(defaults: UserDefaults(suiteName: "olive.c92.transport-tests")!, directory: directory)))
            return
        }
        if args.contains("--c92-pairing-check") {
            let directory = URL.applicationSupportDirectory.appendingPathComponent("C92PairingAcceptance")
            let identities = ConnectIdentityStore(secrets: KeychainSecretStore(service: "olive.c92.pairing-acceptance"))
            let session = ConnectSession(repository: ConnectTrustRepository(directory: directory.appendingPathComponent("Connect")), identities: identities)
            _state = State(initialValue: AppState(store: LocalShellStore(defaults: UserDefaults(suiteName: "olive.c92.pairing-acceptance")!, directory: directory), session: session))
            return
        }
        if args.contains("--c92-cleanup-pairing-check") {
            Task {
                let secrets = KeychainSecretStore(service: "olive.c92.pairing-acceptance")
                try? await secrets.remove(account: "mobile-identity-v1")
                try? await secrets.remove(account: "mobile-identity-reservation-v1")
                let directory = URL.applicationSupportDirectory.appendingPathComponent("C92PairingAcceptance")
                try? FileManager.default.removeItem(at: directory)
                UserDefaults.standard.removePersistentDomain(forName: "olive.c92.pairing-acceptance")
            }
        }
        if let index = args.firstIndex(of: "--ui-test-session"), args.indices.contains(index + 1) {
            let session = args[index + 1]
            let defaults = UserDefaults(suiteName: "olive.ui-tests.\(session)")!
            let directory = URL.applicationSupportDirectory.appendingPathComponent("UITests/\(session)")
            _state = State(initialValue: AppState(store: LocalShellStore(defaults: defaults, directory: directory)))
            return
        }
        #endif
        _state = State(initialValue: AppState(store: LocalShellStore(), session: ConnectSession()))
    }
    var body: some Scene {
        WindowGroup {
            RootView().environment(state).preferredColorScheme(.dark).tint(OliveTheme.accent)
                #if DEBUG
                .overlay(alignment: .top) {
                    if ProcessInfo.processInfo.arguments.contains("--c92-pairing-check") {
                        Text("Pairing acceptance · separate test identity").font(.caption).padding(6)
                            .background(.black).foregroundStyle(.white).allowsHitTesting(false)
                    }
                }
                #endif
        }
    }
}
