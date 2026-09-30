import SwiftUI

@main
struct OLIVEMobileApp: App {
    @State private var state: AppState
    init() {
        // UI tests use an isolated preferences domain and protected draft folder.
        // No connected backend is simulated. The opt-in conflict UI fixture is
        // isolated from production data and cannot establish real sync acceptance.
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if ProcessInfo.processInfo.environment["OLIVE_C92_CANCEL_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_EDGE_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_EDIT_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_CONFLICT_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_RESOLVED_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_DELETE_ACCEPTANCE"] == "1" ||
            ProcessInfo.processInfo.environment["OLIVE_C93_FILE_PREPARE_ACCEPTANCE"] == "1" {
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
            let acceptance = AppState(store: LocalShellStore(defaults: UserDefaults(suiteName: "olive.c92.pairing-acceptance")!, directory: directory), session: session)
            ChatUIFixture.seedDrawNote(acceptance)
            _state = State(initialValue: acceptance)
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
            if args.contains("--ui-test-companion") {
                do {
                    let files = directory.appendingPathComponent("Companion/Files")
                    let staging = FileStaging(directory: files); try staging.prepare()
                    let id = "cccccccc-1111-4111-8111-111111111111", peer = "dddddddd-1111-4111-8111-111111111111"
                    let data = Data("Synthetic UI file".utf8), file = try staging.path(id, "bin")
                    try data.write(to: file)
                    let checked = try staging.digest(file)
                    let metadata = try FileMetadata(name: "Synthetic UI file.txt", size: checked.0, sha256: checked.1, mime: "text/plain")
                    let receipt = MobileFileReceipt(id: id, peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date(), received: checked.0, state: "completed")
                    try ProtectedStore<[MobileFileReceipt]>(url: files.appendingPathComponent("receipts-v1.json"), maximumBytes: 8_000_000).save([receipt])
                } catch { assertionFailure("Could not prepare isolated file UI fixture") }
            }
            let fixture = ChatUIFixture.enabled ? FixtureChatSession(offline: args.contains("--ui-test-chat-offline"),
                                                                     legacy: args.contains("--ui-test-chat-legacy")) : nil
            let isolated = AppState(store: LocalShellStore(defaults: defaults, directory: directory), chatConnection: fixture, drawDefaults: defaults)
            if args.contains("--ui-test-sync-conflict") {
                do {
                    let phone = try ConnectIdentity.generate(), desktop = try ConnectIdentity.generate()
                    let base = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "UI fixture"), identity: phone)
                    let local = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "UI phone version"), parents: [base], identity: phone)
                    let incoming = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "UI desktop version"), parents: [base], identity: desktop)
                    var snapshot = SyncSnapshot()
                    try MobileSyncStore.put(local, in: &snapshot)
                    _ = try MobileSyncStore.apply(incoming, peer: desktop.publicIdentity.deviceID, in: &snapshot)
                    try isolated.sync.store.commit(snapshot); isolated.sync.reload()
                } catch { assertionFailure("Could not prepare isolated sync conflict fixture") }
            }
            if args.contains("--ui-test-companion") { isolated.studio.prepareOfflineUIFixture() }
            if args.contains("--ui-test-long-chat") { isolated.prepareLongChatUIFixture() }
            ChatUIFixture.seedDrawNote(isolated)
            _state = State(initialValue: isolated)
            return
        }
        #endif
        let production = AppState(store: LocalShellStore(), session: ConnectSession())
        _state = State(initialValue: production)
        #if DEBUG
        // Opt-in owned acceptance fixture: select only, never initiate a send.
        // This bypasses the document picker, not C6 or its desktop permissions.
        if let index = args.firstIndex(of: "--c93-select-owned-file"), args.indices.contains(index + 1),
           UUID(uuidString: args[index + 1])?.uuidString.lowercased() == args[index + 1] {
            let directory = URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/FileBackground/" + args[index + 1])
            let source = directory.appendingPathComponent("olive-c93-64MiB.bin")
            Task {
                defer { try? FileManager.default.removeItem(at: source); try? FileManager.default.removeItem(at: directory) }
                let checked = try? await Task.detached { try FileStaging(directory: directory).digest(source) }.value
                guard checked?.0 == 67108864, checked?.1 == "281e519df3077b557c6b03f5da83c4e8d397219259615dd7c3308f89cae8f2a6",
                      production.background?.active == nil else { return }
                await production.files.select(source)
            }
        }
        #endif
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
