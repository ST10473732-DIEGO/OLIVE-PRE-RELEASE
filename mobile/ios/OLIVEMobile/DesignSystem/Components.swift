import SwiftUI

struct OliveMark: View {
    var size: CGFloat = 44
    var body: some View {
        Image("OliveMark").resizable().scaledToFit().frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

struct OliveCard<Content: View>: View {
    @ViewBuilder let content: Content
    var body: some View {
        content.padding(OliveTheme.Space.medium).frame(maxWidth: .infinity, alignment: .leading)
            .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card).stroke(OliveTheme.border))
    }
}

struct OliveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.headline).padding(.horizontal, 16)
            .frame(minHeight: OliveTheme.minimumTouchTarget)
            .foregroundStyle(OliveTheme.accentInk)
            .background(OliveTheme.accent.opacity(configuration.isPressed ? 0.8 : 1),
                        in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control))
    }
}

struct ConnectionBadge: View {
    let state: MobileConnectionState
    var body: some View {
        Label(state.title, systemImage: "link.badge.plus")
            .font(.subheadline).foregroundStyle(OliveTheme.secondary)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(OliveTheme.raised, in: Capsule())
            .accessibilityIdentifier("connection.status")
    }
}

struct OliveEmptyState: View {
    let symbol: String
    let title: String
    let detail: String
    var body: some View {
        VStack(alignment: .leading, spacing: OliveTheme.Space.medium) {
            Image(systemName: symbol).font(.largeTitle).foregroundStyle(OliveTheme.accent)
                .accessibilityHidden(true)
            Text(title).font(OliveTheme.TypeStyle.heading).accessibilityAddTraits(.isHeader)
            Text(detail).font(.body).foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct OliveSectionHeader: View {
    let title: String
    var body: some View {
        Text(title).font(.headline).foregroundStyle(OliveTheme.secondary).accessibilityAddTraits(.isHeader)
    }
}

struct SettingsButton: View {
    @Environment(AppState.self) private var state
    var body: some View {
        Button { state.isSettingsPresented = true } label: {
            Image(systemName: "gearshape").frame(minWidth: 44, minHeight: 44)
        }.accessibilityLabel("Settings").accessibilityIdentifier("settings.open")
    }
}
