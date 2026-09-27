import Foundation
import Observation
import UserNotifications

@MainActor @Observable
final class CompletionNotifications {
    private let defaults: UserDefaults
    private(set) var enabled: Bool
    private(set) var notice = ""
    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults; enabled = defaults.bool(forKey: "companion.notifications.v1")
    }
    func setEnabled(_ value: Bool) async {
        if value {
            do {
                enabled = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
                notice = enabled ? "Completion notifications enabled." : "Notifications are disabled in iOS Settings."
            } catch { enabled = false; notice = "Notifications are unavailable." }
        } else { enabled = false }
        defaults.set(enabled, forKey: "companion.notifications.v1")
    }
    static func message(for capability: String) -> String {
        capability.hasPrefix("files.") ? "File transfer complete" : capability.hasPrefix("studio.") ? "Studio operation finished" : "Response ready"
    }
    func completed(_ record: BackgroundOperationRecord) {
        guard enabled, record.state == .completed else { return }
        let content = UNMutableNotificationContent(); content.title = "OLIVE"; content.body = Self.message(for: record.capability)
        let request = UNNotificationRequest(identifier: "olive.operation." + record.id, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request) { _ in }
    }
}
