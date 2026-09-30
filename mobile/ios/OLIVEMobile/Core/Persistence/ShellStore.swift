import Foundation

@MainActor
protocol ShellStore {
    var companionDirectory: URL? { get }
    func loadDestination() -> Destination
    func saveDestination(_ destination: Destination)
    func loadDraft() throws -> String
    func saveDraft(_ draft: String) throws
    func loadDrawNoteSection() -> DrawNoteSection
    func saveDrawNoteSection(_ section: DrawNoteSection)
}

extension ShellStore {
    var companionDirectory: URL? { nil }
    func loadDrawNoteSection() -> DrawNoteSection { .notes }
    func saveDrawNoteSection(_ section: DrawNoteSection) {}
}

/// Navigation is non-secret preferences. Draft text is a protected, local-only
/// file, excluded from backup; this is not a desktop conversation repository.
@MainActor
final class LocalShellStore: ShellStore {
    private let defaults: UserDefaults
    private let directory: URL
    var companionDirectory: URL? { directory.lastPathComponent == "Shell" ? directory.deletingLastPathComponent().appendingPathComponent("Companion") : directory.appendingPathComponent("Companion") }
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
    /// OLIVE DrawNote remembers its last section on this phone (never synced).
    func loadDrawNoteSection() -> DrawNoteSection {
        DrawNoteSection(rawValue: defaults.string(forKey: "shell.v1.drawnote.section") ?? "") ?? .notes
    }
    func saveDrawNoteSection(_ section: DrawNoteSection) {
        defaults.set(section.rawValue, forKey: "shell.v1.drawnote.section")
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
