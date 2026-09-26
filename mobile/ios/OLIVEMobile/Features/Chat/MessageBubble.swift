import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                if message.role == .assistant { OliveMark(size: 24) }
                Text(message.author).font(.subheadline.weight(.semibold))
            }
            ForEach(Array(message.blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case .text(let text): Text(text).textSelection(.enabled)
                case .code(let language, let content): CodeBlock(language: language, content: content)
                }
            }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(message.role == .user ? OliveTheme.raised : OliveTheme.surface,
                        in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card))
    }
}

struct CodeBlock: View {
    let language: String?
    let content: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language ?? "Code").font(.caption).foregroundStyle(OliveTheme.secondary)
            ScrollView(.horizontal) {
                Text(content).font(OliveTheme.TypeStyle.code).textSelection(.enabled)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }.padding(12).background(OliveTheme.ground, in: RoundedRectangle(cornerRadius: 10))
    }
}
