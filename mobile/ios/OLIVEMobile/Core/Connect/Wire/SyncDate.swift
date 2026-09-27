import Foundation

/// Validation only: never generates flattened recurrence instances or changes
/// portable source times. Native C5 stores civil dates and zoned instants distinctly.
enum SyncDate {
    static func parse(_ text: String, zoned: Bool = false, dateOnly: Bool = false) throws -> Date {
        guard text.utf8.count <= 80, text.count >= 10 else { throw ConnectFailure.responseMalformed }
        let day = String(text.prefix(10))
        let formatter = DateFormatter(); formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"; formatter.isLenient = false
        guard let date = formatter.date(from: day), formatter.string(from: date) == day else { throw ConnectFailure.responseMalformed }
        if text.count == 10 { guard !zoned else { throw ConnectFailure.responseMalformed }; return date }
        guard !dateOnly, text.range(of: #"^\d{4}-\d{2}-\d{2}[T ]([01]\d|2[0-3]):[0-5]\d(:[0-5]\d(\.\d{1,6})?)?(Z|[+-]([01]\d|2[0-3]):[0-5]\d)?$"#, options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
        let hasZone = text.hasSuffix("Z") || text.dropFirst(10).contains("+") || text.dropFirst(10).contains("-")
        guard !zoned || hasZone else { throw ConnectFailure.responseMalformed }
        var value = text.replacingOccurrences(of: " ", with: "T")
        if value.count == 16 { value += ":00" }
        if !hasZone { value += "Z" }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = value.contains(".") ? [.withInternetDateTime, .withFractionalSeconds] : [.withInternetDateTime]
        guard let instant = iso.date(from: value) else { throw ConnectFailure.responseMalformed }
        return instant
    }
    static func nativeInstant(_ text: String, zone: String) throws -> Date {
        let date = try parse(text, zoned: true)
        guard let timezone = TimeZone(identifier: zone), !text.hasSuffix("Z") else { throw ConnectFailure.responseMalformed }
        let suffix = String(text.suffix(6)), hours = Int(suffix.dropFirst().prefix(2)), minutes = Int(suffix.suffix(2))
        guard let hours, let minutes else { throw ConnectFailure.responseMalformed }
        let offset = (hours * 3600 + minutes * 60) * (suffix.first == "-" ? -1 : 1)
        guard timezone.secondsFromGMT(for: date) == offset else { throw ConnectFailure.responseMalformed }
        return date
    }
}
