import Foundation
import Observation

@MainActor @Observable
final class AppState {
    var destination: Destination { didSet { store.saveDestination(destination) } }
    var draft: String { didSet { saveDraft() } }
    var isSettingsPresented = false
    private(set) var persistenceNotice: String?
    let connection: MobileConnectionState = .notPaired
    let messages: [ChatMessage] = []
    let connectClient: any ConnectClient
    let pairingService: any PairingService
    @ObservationIgnored private let store: any ShellStore
    @ObservationIgnored private var canWriteDraft = true
    var canSend: Bool { false } // No transport exists in C9.1; never consume a draft.

    init(store: any ShellStore, connectClient: any ConnectClient = DisconnectedConnectClient(),
         pairingService: any PairingService = UnavailablePairingService()) {
        self.store = store
        self.connectClient = connectClient
        self.pairingService = pairingService
        destination = store.loadDestination()
        do { draft = try store.loadDraft() }
        catch {
            draft = ""
            canWriteDraft = false // Preserve an unreadable/newer file, never overwrite it.
            persistenceNotice = "Your saved draft could not be opened. New text stays here until you close OLIVE."
        }
    }
    func saveDraft() {
        guard canWriteDraft else { return }
        do { try store.saveDraft(draft); persistenceNotice = nil }
        catch { persistenceNotice = "Your draft could not be saved. Keep OLIVE open to retain this text." }
    }
    func openChat() { destination = .chat }
}
