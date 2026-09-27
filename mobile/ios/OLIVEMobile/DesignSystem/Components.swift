import SwiftUI

struct OliveMark: View {
    var size: CGFloat = 44
    var body: some View {
        Image("OliveMark").resizable().scaledToFit().frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

struct OliveCard<Content: View>: View {
    var padding: CGFloat = OliveTheme.Space.medium
    @ViewBuilder let content: Content
    var body: some View {
        content.padding(padding).frame(maxWidth: .infinity, alignment: .leading)
            .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous).stroke(OliveTheme.border))
    }
}

struct OliveButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, destructive }
    var kind: Kind = .primary
    var fullWidth = false
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.headline).lineLimit(2).multilineTextAlignment(.center)
            .padding(.horizontal, 18).padding(.vertical, 10)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: OliveTheme.minimumTouchTarget)
            .foregroundStyle(foreground)
            .background(background, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous)
                .stroke(kind == .primary ? .clear : OliveTheme.border))
            .opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.45)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(OliveTheme.Motion.press, value: configuration.isPressed)
    }
    private var foreground: Color {
        switch kind { case .primary: OliveTheme.accentInk; case .secondary: OliveTheme.text; case .destructive: OliveTheme.attention }
    }
    private var background: Color {
        switch kind { case .primary: OliveTheme.accent; case .secondary: OliveTheme.surface; case .destructive: OliveTheme.attention.opacity(0.12) }
    }
}

/// Gentle press feedback for cards and tiles that act as buttons.
struct OlivePressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.contentShape(Rectangle())
            .scaleEffect(configuration.isPressed ? 0.98 : 1).opacity(configuration.isPressed ? 0.9 : 1)
            .animation(OliveTheme.Motion.press, value: configuration.isPressed)
    }
}

/// Coloured state dot; a soft halo breathes while `pulsing` unless Reduce Motion is on.
struct StatusDot: View {
    var color: Color
    var pulsing = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var expanded = false
    var body: some View {
        Circle().fill(color).frame(width: 8, height: 8)
            .background(Circle().fill(color.opacity(0.35)).scaleEffect(expanded ? 2.4 : 1).opacity(expanded ? 0 : 1))
            .onAppear { animate() }.onChange(of: pulsing) { _, _ in animate() }
            .accessibilityHidden(true)
    }
    private func animate() {
        withAnimation(.easeOut(duration: 0.2)) { expanded = false }
        guard pulsing, !reduceMotion else { return }
        withAnimation(.easeOut(duration: 1.6).repeatForever(autoreverses: false)) { expanded = true }
    }
}

extension MobileConnectionState {
    var tint: Color { self == .connected ? OliveTheme.accent : self == .offline ? OliveTheme.attention : OliveTheme.muted }
}

struct ConnectionBadge: View {
    let state: MobileConnectionState
    var body: some View {
        HStack(spacing: 8) {
            StatusDot(color: state.tint, pulsing: state == .connected)
            Text(state.title).font(.subheadline.weight(.medium)).foregroundStyle(OliveTheme.text)
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(state.tint.opacity(0.12), in: Capsule())
        .overlay(Capsule().stroke(state.tint.opacity(0.3)))
        .animation(OliveTheme.Motion.settle, value: state)
        .accessibilityIdentifier("connection.status")
    }
}

/// Rounded icon well used for tiles, list rows and empty states.
struct OliveIcon: View {
    let symbol: String
    var size: CGFloat = 40
    var tint: Color = OliveTheme.accent
    var body: some View {
        Image(systemName: symbol).font(.system(size: size * 0.45, weight: .semibold)).foregroundStyle(tint)
            .frame(width: size, height: size)
            .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: size * 0.3, style: .continuous))
            .accessibilityHidden(true)
    }
}

struct OliveEmptyState: View {
    let symbol: String
    let title: String
    let detail: String
    var body: some View {
        VStack(spacing: OliveTheme.Space.medium) {
            OliveIcon(symbol: symbol, size: 64)
            VStack(spacing: 6) {
                Text(title).font(OliveTheme.TypeStyle.heading).accessibilityAddTraits(.isHeader)
                Text(detail).font(.body).foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }.multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.vertical, OliveTheme.Space.medium)
    }
}

struct OliveSectionHeader: View {
    let title: String
    var detail: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased()).font(.footnote.weight(.semibold)).tracking(1.2).foregroundStyle(OliveTheme.muted)
                .accessibilityLabel(title).accessibilityAddTraits(.isHeader)
            if let detail { Text(detail).font(.subheadline).foregroundStyle(OliveTheme.secondary) }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 4)
    }
}

/// A label/value line that stacks vertically when the text no longer fits side by side.
struct OliveDetailRow: View {
    let symbol: String
    let title: String
    let value: String
    var valueTint: Color = OliveTheme.secondary
    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { label; Spacer(minLength: 8); valueText.multilineTextAlignment(.trailing) }
            VStack(alignment: .leading, spacing: 4) { label; valueText.padding(.leading, 32) }
        }
        .padding(.vertical, 8).accessibilityElement(children: .combine)
    }
    private var label: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.subheadline).foregroundStyle(OliveTheme.muted).frame(width: 20)
            Text(title).font(.subheadline).foregroundStyle(OliveTheme.text)
        }
    }
    private var valueText: some View { Text(value).font(.subheadline).foregroundStyle(valueTint) }
}

/// Three softly bouncing dots for indeterminate work.
struct OliveActivityDots: View {
    var color: Color = OliveTheme.accent
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(paused: reduceMotion)) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { index in
                    let phase = reduceMotion ? 0 : (sin(time * 5 - Double(index) * 0.8) + 1) / 2
                    Circle().fill(color).frame(width: 7, height: 7)
                        .opacity(0.35 + 0.65 * phase).offset(y: -3 * phase)
                }
            }
        }.frame(height: 14).accessibilityHidden(true)
    }
}

extension View {
    /// Centres content in a readable column with consistent gutters in portrait and landscape.
    func olivePage(top: CGFloat = OliveTheme.Space.medium) -> some View {
        padding(.horizontal, OliveTheme.Space.medium).padding(.top, top).padding(.bottom, OliveTheme.Space.section)
            .frame(maxWidth: OliveTheme.pageWidth).frame(maxWidth: .infinity)
    }
    /// Fades and lifts content in on first appearance, staggered by `order`.
    func oliveAppear(_ order: Int = 0) -> some View { modifier(OliveAppear(order: order)) }
}

private struct OliveAppear: ViewModifier {
    let order: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false
    func body(content: Content) -> some View {
        content.opacity(shown ? 1 : 0).offset(y: shown || reduceMotion ? 0 : 14)
            .onAppear {
                guard !shown else { return }
                withAnimation(reduceMotion ? .easeOut(duration: 0.2) : OliveTheme.Motion.appear.delay(Double(order) * 0.06)) { shown = true }
            }
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
