import Foundation

enum Destination: String, CaseIterable {
    case home, chat, notes, devices
    var title: String { self == .notes ? "OLIVE Notes" : rawValue.capitalized }
    var symbol: String {
        switch self {
        case .home: "house"
        case .chat: "bubble.left.and.bubble.right"
        case .notes: "note.text"
        case .devices: "laptopcomputer.and.iphone"
        }
    }
}
