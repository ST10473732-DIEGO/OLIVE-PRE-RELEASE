import Foundation

struct AboutInfo {
    let name: String
    let version: String
    let build: String
    init(info: [String: Any] = Bundle.main.infoDictionary ?? [:]) {
        name = info["CFBundleDisplayName"] as? String ?? "OLIVE"
        version = info["CFBundleShortVersionString"] as? String ?? "Unknown"
        build = info["CFBundleVersion"] as? String ?? "Unknown"
    }
    var versionDescription: String { "\(version) (\(build))" }
}
