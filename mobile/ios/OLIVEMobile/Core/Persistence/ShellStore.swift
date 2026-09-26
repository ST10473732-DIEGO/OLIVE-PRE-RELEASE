import Foundation

@MainActor
protocol ShellStore {
    func loadDestination() -> Destination
    func saveDestination(_ destination: Destination)
    func loadDraft() throws -> String
    func saveDraft(_ draft: String) throws
}

/// Navigation is non-secret preferences. Draft text is a protected, local-only
/// file, excluded from backup; this is not a desktop conversation repository.
@MainActor
final class LocalShellStore: ShellStore {
    private let defaults: UserDefaults
    private let directory: URL
    private var draftURL: URL { directory.appendingPathComponent("draft-v1.json") }
    private struct Draft: Codable { let version: Int; let text: String }
    enum StoreError: Error { case unsupportedVersion }

    init(defaults: UserDefaults = .standard, directory: URL? = nil) {
        self.defaults = defaults
        self.directory = directory ?? URL.applicationSupportDirectory.appendingPathComponent("Shell", isDirectory: true)
    }
    func loadDestination() -> Destination {
        Destination(rawValue: defaults.string(forKey: "shell.v1.destination") ?? "") ?? .home
    }
    func saveDestination(_ destination: Destination) {
        defaults.set(destination.rawValue, forKey: "shell.v1.destination")
    }
    func loadDraft() throws -> String {
        guard FileManager.default.fileExists(atPath: draftURL.path) else { return "" }
        let draft = try JSONDecoder().decode(Draft.self, from: Data(contentsOf: draftURL))
        guard draft.version == 1 else { throw StoreError.unsupportedVersion }
        return draft.text
    }
    func saveDraft(_ draft: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                               attributes: [.protectionKey: FileProtectionType.complete])
        var localDirectory = directory
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try localDirectory.setResourceValues(values)
        let data = try JSONEncoder().encode(Draft(version: 1, text: draft))
        try data.write(to: draftURL, options: [.atomic, .completeFileProtection])
    }
}
