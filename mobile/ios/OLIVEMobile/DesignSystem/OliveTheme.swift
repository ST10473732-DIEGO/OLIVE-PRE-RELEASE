import SwiftUI

/// Grove semantic tokens; solid surfaces deliberately avoid decorative glass.
enum OliveTheme {
    static let ground = Color(hex: 0x060705)
    static let surface = Color(hex: 0x121510)
    static let raised = Color(hex: 0x20251B)
    static let text = Color(hex: 0xE9ECE1)
    static let secondary = Color(hex: 0xBFC5B3)
    static let muted = Color(hex: 0x939A87)
    static let accent = Color(hex: 0xB9C67C)
    static let accentInk = Color(hex: 0x151A07)
    static let information = Color(hex: 0x86B3EC)
    static let attention = Color(hex: 0xEF6E51)
    static let border = Color(hex: 0xE2ECC8).opacity(0.19)
    enum Space {
        static let small: CGFloat = 8
        static let medium: CGFloat = 16
        static let page: CGFloat = 24
        static let section: CGFloat = 32
    }
    enum Radius {
        static let control: CGFloat = 12
        static let card: CGFloat = 18
        static let composer: CGFloat = 22
    }
    /// Readable column width; pages centre within it in both orientations.
    static let pageWidth: CGFloat = 640
    enum Motion {
        static let press = Animation.spring(response: 0.25, dampingFraction: 0.7)
        static let settle = Animation.spring(response: 0.42, dampingFraction: 0.86)
        static let appear = Animation.spring(response: 0.55, dampingFraction: 0.85)
    }
    enum TypeStyle {
        static let display = Font.system(.largeTitle, design: .rounded, weight: .semibold)
        static let heading = Font.system(.title2, design: .rounded, weight: .semibold)
        static let body = Font.body
        static let caption = Font.caption
        static let code = Font.system(.body, design: .monospaced)
    }
    static let minimumTouchTarget: CGFloat = 44
}

private extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 255) / 255,
                  green: Double((hex >> 8) & 255) / 255, blue: Double(hex & 255) / 255, opacity: 1)
    }
}
