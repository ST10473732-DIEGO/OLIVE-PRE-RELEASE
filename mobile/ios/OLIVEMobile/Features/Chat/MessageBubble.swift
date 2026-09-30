import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage
    var thinking = false
    private var isUser: Bool { message.role == .user }
    private var isEmpty: Bool { message.plainText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if isUser { Spacer(minLength: 48) } else { OliveMark(size: 28).padding(.top, 2) }
            VStack(alignment: isUser ? .trailing : .leading, spacing: 8) {
                if !isUser { Text(message.author).font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.muted) }
                if thinking && isEmpty {
                    OliveActivityDots().padding(.vertical, 6).accessibilityLabel("OLIVE is responding")
                }
                if isUser && !message.attachments.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) { ForEach(message.attachments) { AttachmentChip(item: $0) } }
                    }.frame(maxWidth: 320).accessibilityIdentifier("chat.message.attachments")
                }
                ForEach(Array(message.blocks.enumerated()), id: \.offset) { _, block in
                    switch block {
                    case .text(let text): Text(text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    case .code(let language, let content): CodeBlock(language: language, content: content)
                    }
                }
                ForEach(message.artifacts) { ArtifactView(artifact: $0) }
                if !message.sources.isEmpty { SourcesView(sources: message.sources) }
                if let status = message.status { Text(status).font(.caption).foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(isUser ? "chat.message.status.user" : "chat.message.status") }
                if !isUser, let label = message.modeLabel {
                    Text(label).font(.caption2.weight(.medium)).foregroundStyle(OliveTheme.muted)
                        .accessibilityLabel("Answered by " + label.replacingOccurrences(of: " · ", with: ", "))
                        .accessibilityIdentifier("chat.message.attribution")
                }
            }
            .padding(isUser ? 14 : 0)
            .background(isUser ? OliveTheme.raised : .clear, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous)
                .stroke(isUser ? OliveTheme.accent.opacity(0.22) : .clear))
            .frame(maxWidth: isUser ? nil : .infinity, alignment: .leading)
            if !isUser { Spacer(minLength: 0) }
        }
        .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
    }
}

struct CodeBlock: View {
    let language: String?
    let content: String
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(language?.isEmpty == false ? language! : "Code").font(.caption.weight(.medium)).foregroundStyle(OliveTheme.secondary)
                Spacer()
                Button { UIPasteboard.general.string = content } label: {
                    Image(systemName: "doc.on.doc").font(.caption).frame(minWidth: 32, minHeight: 28)
                }.foregroundStyle(OliveTheme.muted).accessibilityLabel("Copy code")
            }.padding(.leading, 12).padding(.trailing, 4).padding(.vertical, 2)
                .background(OliveTheme.raised.opacity(0.6))
            ScrollView(.horizontal, showsIndicators: false) {
                Text(content).font(OliveTheme.TypeStyle.code).textSelection(.enabled)
                    .fixedSize(horizontal: true, vertical: false).padding(12)
            }
        }
        .background(OliveTheme.ground, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous).stroke(OliveTheme.border))
    }
}
