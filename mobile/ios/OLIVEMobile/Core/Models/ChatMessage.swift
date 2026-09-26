import Foundation

/// Presentation model only. No separate persisted mobile chat database.
struct ChatMessage: Identifiable, Equatable {
    enum Role: String { case user, assistant }
    enum Block: Equatable { case text(String), code(language: String?, content: String) }
    let id: UUID
    let role: Role
    let blocks: [Block]
    var author: String { role == .user ? "You" : "OLIVE" }
}
