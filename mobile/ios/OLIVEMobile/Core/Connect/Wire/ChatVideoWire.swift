import Foundation

/// OLIVE VIDEO over olive-chat/1 (mode_options/1 extension): what the computer's
/// VIDEO engine supports, structured long-video progress, and the phone's copy
/// of the deterministic duration parser (olive/services/video_duration.py; the
/// shared vectors in OLIVEMobileTests keep the two identical).
///
/// Everything here is advisory display data from the computer, bounded and
/// tolerant of additive keys. The computer owns planning, limits and generation.
struct VideoCapability: Equatable, Sendable {
    let textToVideo: Bool
    let imageToVideo: Bool
    let audio: Bool
    let nativeSegmentMS: Int64
    let fps: Int
    let maxImages: Int
    let configurable: Bool
    let defaultMS: Int64
    let minimumMS: Int64
    let maximumMS: Int64
    let longWarningMS: Int64
    let presetsMS: [Int64]

    static let ceilingMS: Int64 = 3_600_000

    init(_ v: ConnectJSON) throws {
        guard v.object != nil else { throw ConnectFailure.responseMalformed }
        func flag(_ value: ConnectJSON) throws -> Bool {
            guard let boolean = value.boolean else { throw ConnectFailure.responseMalformed }
            return boolean
        }
        let limit: ClosedRange<Int64> = 0...Self.ceilingMS
        textToVideo = try flag(v["supports_text_to_video"]); imageToVideo = try flag(v["supports_image_to_video"])
        audio = try flag(v["supports_audio"])
        nativeSegmentMS = try v["native_segment_ms"].number(limit)
        fps = Int(try v["fps"].number(0...240)); maxImages = Int(try v["max_images"].number(0...8))
        let d = v["duration"]
        configurable = try flag(d["configurable"])
        defaultMS = try d["default_ms"].number(limit); minimumMS = try d["minimum_ms"].number(limit)
        maximumMS = try d["maximum_ms"].number(limit); longWarningMS = try d["long_warning_ms"].number(limit)
        guard let presets = d["presets_ms"].array, presets.count <= 12 else { throw ConnectFailure.responseMalformed }
        presetsMS = try presets.map { try $0.number(1...Self.ceilingMS) }
    }

    init(imageToVideo: Bool, configurable: Bool = true, defaultMS: Int64 = 2000, minimumMS: Int64 = 500, maximumMS: Int64 = 180_000,
         longWarningMS: Int64 = 30_000, presetsMS: [Int64] = [2000, 5000, 10000, 20000, 30000, 60000]) {
        textToVideo = true; self.imageToVideo = imageToVideo; audio = true; nativeSegmentMS = 2042; fps = 24
        maxImages = imageToVideo ? 1 : 0; self.configurable = configurable; self.defaultMS = defaultMS; self.minimumMS = minimumMS
        self.maximumMS = maximumMS; self.longWarningMS = longWarningMS; self.presetsMS = presetsMS
    }

    /// Native segments the computer will render for a target (for the phone's own patience only).
    func segments(forMS target: Int64) -> Int {
        let frames = max(1, Int((Double(target) / 1000 * 24).rounded()))
        return frames <= 49 ? 1 : 1 + Int((Double(frames - 49) / 48).rounded(.up))
    }
}

/// Real long-video progress the computer observed ("segment 3 of 10"). Never a percentage.
struct ChatProgress: Equatable, Sendable {
    let stage: String
    let current: Int
    let total: Int
    static let stages: Set<String> = ["segment", "continuation", "stitching", "encoding", "verifying", "saving"]

    /// nil for null or a stage this build does not know (a newer computer's additions).
    init?(_ v: ConnectJSON) throws {
        guard v != .null else { return nil }
        guard v.object != nil, let stage = v["stage"].string, stage.utf8.count <= 32 else { throw ConnectFailure.responseMalformed }
        let current = Int(try v["current"].number(1...100_000)), total = Int(try v["total"].number(1...100_000))
        guard current <= total else { throw ConnectFailure.responseMalformed }
        guard Self.stages.contains(stage) else { return nil }
        self.stage = stage; self.current = current; self.total = total
    }

    init(stage: String, current: Int, total: Int) { self.stage = stage; self.current = current; self.total = total }

    var text: String {
        switch stage {
        case "segment": total > 1 ? "Generating segment \(current) of \(total)…" : "Generating video…"
        case "continuation": "Extracting continuation frame…"
        case "stitching": "Stitching \(total) segments…"
        case "encoding": "Encoding final video…"
        case "verifying": "Verifying output…"
        default: "Saving result…"
        }
    }
}

/// Duration stated in a VIDEO prompt. A port of olive/services/video_duration.py
/// `parse_duration`: the same strong contexts, the same first-match rule.
enum VideoDuration {
    struct Match: Equatable { let seconds: Double; let range: NSRange }

    private static let words: [String: Double] = [
        "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
        "forty-five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
    ]
    private static let number = "(?:\\d{1,6}(?:\\.\\d{1,3})?|" + words.keys.sorted { ($0.count, $1) > ($1.count, $0) }
        .map(NSRegularExpression.escapedPattern(for:)).joined(separator: "|") + ")"
    private static let unit = "(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|h|m|s)"
    private static let part = "\(number)(?:\\s*-\\s*|\\s*)\(unit)(?![a-z])"
    private static let half = "half(?:\\s+an?|\\s*-)?\\s*(?:minute|hour)(?![a-z])"
    private static let duration = "(?:\(half)|\(part)(?:\\s*(?:,|and)?\\s*\(part))*(?:\\s+and\\s+a\\s+half)?)"
    private static let nouns = "(?:video|clip|scene|shot|animation|movie|film|sequence|timelapse|time-lapse|loop|footage|cinematic)"
    private static func regex(_ pattern: String) -> NSRegularExpression {
        // swiftlint:disable:next force_try
        try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
    }
    /// (pattern, whole match is the removable span)
    private static let strong: [(NSRegularExpression, Bool)] = [
        (regex("(?<d>\(duration))(?:\\s*-?\\s*long)?(?=\\s+(?:[a-z-]+\\s+){0,3}\(nouns)\\b)"), false),
        (regex("(?<lead>\\b(?:for|lasting|lasts|duration(?:\\s+of)?|length(?:\\s+of)?|runtime|total\\s+of)\\s*:?\\s*)(?<d>\(duration))"), true),
        (regex("(?<d>\(duration))(?<tail>\\s+(?:long\\b|of\\s+))"), true),
        (regex("(?:^|(?<=[,;:(\\[]))\\s*(?<d>\(duration))\\s*(?=$|[,;:.!)\\]])"), false),
    ]
    private static let clock = regex("(?<![\\d:.])(\\d{1,2}):([0-5]\\d)(?::([0-5]\\d))?(?![\\d:])")
    private static let clockExcluded = regex("\\b(?:at|by|until|till|from|to|before|after|around)\\s*$")
    private static let clockSuffix = regex("^\\s*(?:a\\.?m\\.?|p\\.?m\\.?|o'?clock|h\\b|hrs?\\b|hours?\\b)")
    private static let parts = regex("(\(number))(?:\\s*-\\s*|\\s*)(\(unit))(?![a-z])")
    private static let halfOnly = regex("^half(?:\\s+an?|\\s*-)?\\s*(minute|hour)$")
    private static let andHalf = regex("and\\s+a\\s+half$")
    private static let bareS = regex("^\\s*\\d{1,4}s\\s*$")
    private static let bareSPrefix = regex("\\b(?:the|her|his|their|my|your|our|in|early|late|mid)\\s*$|'$")

    private static func found(_ re: NSRegularExpression, _ text: String) -> Bool {
        re.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil
    }

    static func seconds(of expression: String) -> Double? {
        let text = expression.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let ns = text as NSString
        if let half = halfOnly.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) {
            return ns.substring(with: half.range(at: 1)) == "minute" ? 30 : 1800
        }
        var total = 0.0, lastUnit: Double?
        for match in parts.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            let token = ns.substring(with: match.range(at: 1)), unit = ns.substring(with: match.range(at: 2))
            let scale: Double = unit.hasPrefix("h") ? 3600 : unit.hasPrefix("m") ? 60 : 1
            total += (words[token] ?? Double(token) ?? 0) * scale
            lastUnit = scale
        }
        guard let lastUnit else { return nil }
        if found(andHalf, text) { total += lastUnit / 2 }
        return total
    }

    /// The first strongly stated clip duration, or nil.
    static func parse(_ text: String) -> Match? {
        let ns = text as NSString
        let all = NSRange(location: 0, length: ns.length)
        var candidates: [(start: Int, seconds: Double, range: NSRange)] = []
        for (pattern, whole) in strong {
            for match in pattern.matches(in: text, range: all) {
                let d = match.range(withName: "d")
                let expression = ns.substring(with: d)
                if found(bareS, expression), found(bareSPrefix, ns.substring(to: d.location)) { continue }
                guard let seconds = seconds(of: expression), seconds > 0 else { continue }
                candidates.append((d.location, seconds, whole ? match.range : d))
            }
        }
        for match in clock.matches(in: text, range: all) {
            if found(clockExcluded, ns.substring(to: match.range.location))
                || found(clockSuffix, ns.substring(from: match.range.location + match.range.length)) { continue }
            let a = Int(ns.substring(with: match.range(at: 1))) ?? 0, b = Int(ns.substring(with: match.range(at: 2))) ?? 0
            let c = match.range(at: 3).location == NSNotFound ? nil : Int(ns.substring(with: match.range(at: 3)))
            let seconds = c.map { a * 3600 + b * 60 + $0 } ?? a * 60 + b
            if seconds > 0 { candidates.append((match.range.location, Double(seconds), match.range)) }
        }
        var best: (start: Int, seconds: Double, range: NSRange)?
        for candidate in candidates where best == nil || candidate.start < best!.start { best = candidate }
        return best.map { Match(seconds: $0.seconds, range: $0.range) }
    }

    /// "20 s", "1 min", "1 min 30 s", "2.5 s".
    static func label(_ seconds: Double) -> String {
        if seconds < 60 {
            return (seconds == seconds.rounded() ? String(Int(seconds)) : String(format: "%.1f", seconds)) + " s"
        }
        let whole = Int(seconds.rounded()), minutes = whole / 60, rest = whole % 60
        return "\(minutes) min" + (rest > 0 ? " \(rest) s" : "")
    }

    /// A custom entry in seconds or minutes; nil unless a positive, bounded number.
    static func custom(_ text: String, minutes: Bool) -> Double? {
        let value = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard value.range(of: "^\\d{1,5}(\\.\\d{1,3})?$", options: .regularExpression) != nil, let number = Double(value) else { return nil }
        let seconds = number * (minutes ? 60 : 1)
        return seconds > 0 ? (seconds * 1000).rounded() / 1000 : nil
    }
}
