import Foundation

enum Destination: String, CaseIterable {
    case home, chat, devices
    var title: String { rawValue.capitalized }
    var symbol: String {
        switch self {
        case .home: "house"
        case .chat: "bubble.left.and.bubble.right"
        case .devices: "laptopcomputer.and.iphone"
        }
    }
}
