import Foundation

enum Destination: String, CaseIterable {
    case home, chat, notes, devices
    /// `.notes` is the OLIVE DrawNote tab (Notes | Draw); the raw value is kept
    /// so a saved destination still opens it.
    var title: String { self == .notes ? "OLIVE DrawNote" : rawValue.capitalized }
    var symbol: String {
        switch self {
        case .home: "house"
        case .chat: "bubble.left.and.bubble.right"
        case .notes: "square.and.pencil"
        case .devices: "laptopcomputer.and.iphone"
        }
    }
}
