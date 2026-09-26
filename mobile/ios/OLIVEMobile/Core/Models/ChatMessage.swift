import Foundation

/// Presentation model only. No separate persisted mobile chat database.
struct ChatMessage: Identifiable, Equatable {
    enum Role: String { case user, assistant }
    enum Block: Equatable { case text(String), code(language: String?, content: String) }
    let id: UUID
    let role: Role
    let blocks: [Block]
    var status: String? = nil
    var attribution: Attribution? = nil
    struct Attribution: Equatable { let runtime = "OLIVE Connect"; let deviceID: String; let preset: String; let requestID: String }
    var author: String { role == .user ? "You" : "OLIVE" }
}

extension ChatMessage {
    var plainText: String { blocks.map { block in
        switch block { case .text(let text): text; case .code(let language, let content): "```" + (language ?? "") + "\n" + content + "\n```" }
    }.joined(separator: "\n") }
    static func parse(_ text: String) -> [Block] {
        var result: [Block] = [], buffer: [String] = [], language: String?, inCode = false
        for line in text.components(separatedBy: "\n") {
            if line.hasPrefix("```") {
                if !buffer.isEmpty { result.append(inCode ? .code(language: language, content: buffer.joined(separator: "\n")) : .text(buffer.joined(separator: "\n"))); buffer = [] }
                inCode.toggle(); language = inCode ? String(line.dropFirst(3)) : nil
            } else { buffer.append(line) }
        }
        if !buffer.isEmpty { result.append(inCode ? .code(language: language, content: buffer.joined(separator: "\n")) : .text(buffer.joined(separator: "\n"))) }
        return result
    }
}
