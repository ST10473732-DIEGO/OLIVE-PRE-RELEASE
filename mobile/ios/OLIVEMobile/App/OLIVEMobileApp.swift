import SwiftUI

@main
struct OLIVEMobileApp: App {
    @State private var state: AppState
    init() {
        // UI tests use an isolated preferences domain and protected draft folder.
        // This contains no synthetic peer, message or connected backend state.
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if let index = args.firstIndex(of: "--ui-test-session"), args.indices.contains(index + 1) {
            let session = args[index + 1]
            let defaults = UserDefaults(suiteName: "olive.ui-tests.\(session)")!
            let directory = URL.applicationSupportDirectory.appendingPathComponent("UITests/\(session)")
            _state = State(initialValue: AppState(store: LocalShellStore(defaults: defaults, directory: directory)))
            return
        }
        #endif
        _state = State(initialValue: AppState(store: LocalShellStore()))
    }
    var body: some Scene {
        WindowGroup {
            RootView().environment(state).preferredColorScheme(.dark).tint(OliveTheme.accent)
        }
    }
}
