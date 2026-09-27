import Foundation

/// Bounded civil-time expansion of the C5 DAILY/WEEKLY/MONTHLY/YEARLY subset.
/// Instances are a view over signed source records, never new sync records.
enum SyncCalendar {
    static var civil: Calendar {
        var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(secondsFromGMT: 0)!
        return c
    }
    static let weekdays = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"]
    struct Rule {
        var frequency = ""
        var interval = 1
        var count: Int?
        var until: Date?
        var months: [Int] = []
        var monthDays: [Int] = []
        var hasMonthDays = false
        var days: [(Int, Int?)] = []
        var weekStart = 2
        init(_ text: String, allDay: Bool) throws {
            guard !text.isEmpty else { return }
            var fields: [String: String] = [:]
            for part in text.split(separator: ";", omittingEmptySubsequences: false) {
                let pair = part.split(separator: "=", omittingEmptySubsequences: false)
                guard pair.count == 2, !pair[1].isEmpty, fields[String(pair[0])] == nil,
                      ["FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "WKST"].contains(String(pair[0])) else { throw ConnectFailure.responseMalformed }
                fields[String(pair[0])] = String(pair[1])
            }
            frequency = fields["FREQ"] ?? ""
            guard ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].contains(frequency), fields["COUNT"] == nil || fields["UNTIL"] == nil else { throw ConnectFailure.responseMalformed }
            func number(_ text: String, _ range: ClosedRange<Int>) throws -> Int {
                guard let n = Int(text), range.contains(n) else { throw ConnectFailure.responseMalformed }; return n
            }
            if let raw = fields["INTERVAL"] { interval = try number(raw, 1...366) }
            if let raw = fields["COUNT"] { count = try number(raw, 1...10000) }
            if let raw = fields["BYMONTH"] { months = try raw.split(separator: ",", omittingEmptySubsequences: false).map { try number(String($0), Int(Int32.min)...Int(Int32.max)) } }
            if let raw = fields["BYMONTHDAY"] { monthDays = try raw.split(separator: ",", omittingEmptySubsequences: false).map {
                try number(String($0), Int(Int32.min)...Int(Int32.max))
            } }
            hasMonthDays = fields["BYMONTHDAY"] != nil
            monthDays.removeAll { $0 == 0 } // dateutil ignores zero month days.
            if let raw = fields["BYDAY"] {
                for part in raw.split(separator: ",", omittingEmptySubsequences: false) {
                    guard let index = weekdays.firstIndex(of: String(part.suffix(2))) else { throw ConnectFailure.responseMalformed }
                    let prefix = String(part.dropLast(2))
                    let ordinal = prefix.isEmpty ? nil : try number(prefix, Int(Int32.min)...Int(Int32.max))
                    guard ordinal != 0 else { throw ConnectFailure.responseMalformed }
                    days.append((index + 1, ordinal))
                }
            }
            if let raw = fields["WKST"] {
                guard let index = weekdays.firstIndex(of: raw) else { throw ConnectFailure.responseMalformed }; weekStart = index + 1
            }
            if let raw = fields["UNTIL"] {
                guard raw.range(of: #"^\d{8}(T\d{6}Z?)?$"#, options: .regularExpression) != nil,
                      allDay ? !raw.hasSuffix("Z") : raw.hasSuffix("Z") else { throw ConnectFailure.responseMalformed }
                let f = DateFormatter(); f.calendar = civil; f.timeZone = civil.timeZone; f.locale = Locale(identifier: "en_US_POSIX")
                f.dateFormat = raw.count == 8 ? "yyyyMMdd" : raw.hasSuffix("Z") ? "yyyyMMdd'T'HHmmss'Z'" : "yyyyMMdd'T'HHmmss"
                f.isLenient = false
                guard let date = f.date(from: raw), f.string(from: date) == raw else { throw ConnectFailure.responseMalformed }
                until = date
            }
        }
    }
    static func wall(_ date: Date, zone: TimeZone) -> Date { date.addingTimeInterval(TimeInterval(zone.secondsFromGMT(for: date))) }
    static func local(_ wall: Date, zone: TimeZone) -> Date? {
        var c = civil; c.timeZone = zone
        let parts = civil.dateComponents([.year, .month, .day, .hour, .minute, .second, .nanosecond], from: wall)
        guard let date = c.date(from: parts), abs(Self.wall(date, zone: zone).timeIntervalSince(wall)) < 0.001 else { return nil }
        return date // Nonexistent spring-forward civil times are skipped, not shifted.
    }
    static func key(_ point: Date, allDay: Bool, zone: TimeZone) -> String {
        let f = DateFormatter(); f.calendar = civil; f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = zone
        f.dateFormat = allDay ? "yyyy-MM-dd" : "yyyy-MM-dd'T'HH:mm:ssxxx"
        let text = f.string(from: point)
        if !allDay {
            let micros = Int((point.timeIntervalSince1970 - floor(point.timeIntervalSince1970)) * 1_000_000 + 0.5) % 1_000_000
            if micros != 0 { return String(text.dropLast(6)) + String(format: ".%06d", micros) + text.suffix(6) }
        }
        return text
    }
    static func bounds(_ value: ConnectJSON) throws -> (Date, Date, TimeZone, Bool) {
        guard let zone = TimeZone(identifier: try value["timezone"].text()) else { throw ConnectFailure.responseMalformed }
        let allDay = value["all_day"] == .bool(true)
        if allDay {
            let start = try SyncDate.parse(value["start"].text(), dateOnly: true), end = try SyncDate.parse(value["end"].text(), dateOnly: true)
            guard let a = local(start, zone: zone), let b = local(end, zone: zone) else { throw ConnectFailure.responseMalformed }
            return (a, b, zone, true)
        }
        return (try SyncDate.nativeInstant(value["start"].text(), zone: zone.identifier), try SyncDate.nativeInstant(value["end"].text(), zone: zone.identifier), zone, false)
    }
    /// Stop callback avoids unbounded generation for finite windows / exceptions.
    static func points(_ value: ConnectJSON, through: Date, visit: (Date) throws -> Void) throws {
        let (start, _, zone, allDay) = try bounds(value)
        let rule = try Rule(value["recurrence"].text(), allDay: allDay)
        if rule.frequency.isEmpty { if start <= through { try visit(start) }; return }
        // dateutil rrule truncates DTSTART microseconds for recurring series.
        let wallStart = wall(Date(timeIntervalSince1970: floor(start.timeIntervalSince1970)), zone: zone), c = civil
        let dayStart = c.startOfDay(for: wallStart), time = wallStart.timeIntervalSince(dayStart)
        let unit: Calendar.Component = rule.frequency == "DAILY" ? .day : rule.frequency == "WEEKLY" ? .weekOfYear : rule.frequency == "MONTHLY" ? .month : .year
        var period = dayStart
        if unit == .weekOfYear { period = c.date(byAdding: .day, value: -((c.component(.weekday, from: dayStart) - rule.weekStart + 7) % 7), to: dayStart)! }
        if unit == .month || unit == .year { period = c.dateInterval(of: unit, for: dayStart)!.start }
        var emitted = 0, candidates = 0, periods = 0
        while c.component(.year, from: period) <= 9999 {
            try Task.checkCancellation()
            periods += 1
            // Empty rules also terminate deterministically; no idle background work.
            guard periods <= 100000 else { throw ConnectFailure.resourceBusy }
            if period > wall(through, zone: zone).addingTimeInterval(86400) { return }
            let dayCount = unit == .day ? 1 : unit == .weekOfYear ? 7 : c.range(of: .day, in: unit, for: period)!.count
            for offset in 0..<dayCount {
                let day = c.date(byAdding: .day, value: offset, to: period)!
                let month = c.component(.month, from: day), monthDay = c.component(.day, from: day), weekday = c.component(.weekday, from: day)
                if !rule.months.isEmpty && !rule.months.contains(month) { continue }
                let length = c.range(of: .day, in: .month, for: day)!.count
                if !rule.monthDays.isEmpty && !rule.monthDays.contains(where: { ($0 > 0 ? $0 : length + $0 + 1) == monthDay }) { continue }
                let ordinalScope = unit == .month || unit == .year
                let plainDays = rule.days.filter { !ordinalScope || $0.1 == nil }
                let ordinalDays = rule.days.filter { ordinalScope && $0.1 != nil }
                if !plainDays.isEmpty && !plainDays.contains(where: { $0.0 == weekday }) { continue }
                // dateutil applies plain and ordinal BYDAY filters independently.
                if !ordinalDays.isEmpty && !ordinalDays.contains(where: { d, n in
                    guard d == weekday, let ordinal = n else { return false }
                    let scope: Calendar.Component = unit == .year && rule.months.isEmpty ? .year : .month
                    let index = c.ordinality(of: .day, in: scope, for: day)!, total = c.range(of: .day, in: scope, for: day)!.count
                    return ordinal > 0 ? (index - 1) / 7 + 1 == ordinal : -((total - index) / 7 + 1) == ordinal
                }) { continue }
                if rule.days.isEmpty && !rule.hasMonthDays {
                    if unit == .weekOfYear && weekday != c.component(.weekday, from: dayStart) { continue }
                    if (unit == .month || unit == .year) && monthDay != c.component(.day, from: dayStart) { continue }
                    if unit == .year && rule.months.isEmpty && month != c.component(.month, from: dayStart) { continue }
                }
                let candidate = day.addingTimeInterval(time)
                if candidate < wallStart { continue }
                candidates += 1; guard candidates <= 100000 else { throw ConnectFailure.resourceBusy }
                guard let point = local(candidate, zone: zone) else { continue }
                if point > through { return }
                if let until = rule.until, (allDay ? candidate : point) > until { return }
                try visit(point); emitted += 1
                if let count = rule.count, emitted >= count { return }
            }
            guard let next = c.date(byAdding: unit, value: rule.interval, to: period), next > period else { return }
            period = next
        }
    }
    static func validateExceptions(_ value: ConnectJSON) throws {
        let (_, _, zone, allDay) = try bounds(value)
        _ = try Rule(value["recurrence"].text(), allDay: allDay)
        guard let exceptions = value["exceptions"].object, exceptions.count <= 500 else { throw ConnectFailure.responseMalformed }
        var latest = Date.distantPast
        for (original, patch) in exceptions {
            let date = allDay ? try SyncDate.parse(original, dateOnly: true) : try SyncDate.nativeInstant(original, zone: zone.identifier)
            latest = max(latest, allDay ? local(date, zone: zone) ?? date : date)
            guard let fields = patch.object, Set(fields.keys).isSubset(of: ["start", "end", "title", "description", "location", "cancelled"]), (fields["start"] == nil) == (fields["end"] == nil) else { throw ConnectFailure.responseMalformed }
            for (name, part) in fields {
                if name == "cancelled" { guard part.boolean != nil else { throw ConnectFailure.responseMalformed } }
                else {
                    let text = try part.text()
                    guard !text.contains("\0"), text.unicodeScalars.count <= (name == "description" ? 8000 : 300), name != "title" || !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw ConnectFailure.responseMalformed }
                }
            }
            if fields["start"] != nil {
                var changed = value.object!; changed.merge(fields.filter { $0.key != "cancelled" }) { _, new in new }
                changed["recurrence"] = .string(""); changed["exceptions"] = .object([:])
                try SyncPayload.validate(kind: "event", value: .object(changed))
            }
        }
        if !exceptions.isEmpty {
            var remaining = Set(exceptions.keys)
            try points(value, through: latest) { remaining.remove(key($0, allDay: allDay, zone: zone)) }
            guard remaining.isEmpty else { throw ConnectFailure.responseMalformed }
        }
    }
    static func occurrences(_ value: ConnectJSON, after: Date, before: Date) throws -> [ConnectJSON] {
        guard before > after, before.timeIntervalSince(after) <= 400 * 86400 else { throw ConnectFailure.responseMalformed }
        if value["status"] == .string("cancelled") { return [] }
        let (start, end, zone, allDay) = try bounds(value)
        let duration = wall(end, zone: zone).timeIntervalSince(wall(start, zone: zone))
        var output: [ConnectJSON] = [], seen = Set<String>()
        func include(_ point: Date, _ original: String) throws {
            guard let finish = local(wall(point, zone: zone).addingTimeInterval(duration), zone: zone) else { return }
            let patch = value["exceptions"][original]
            guard patch["cancelled"] != .bool(true) else { return }
            var item = value.object!
            item["start"] = .string(key(point, allDay: allDay, zone: zone)); item["end"] = .string(key(finish, allDay: allDay, zone: zone))
            if let fields = patch.object { item.merge(fields.filter { $0.key != "cancelled" }) { _, new in new } }
            let (a, b, _, _) = try bounds(.object(item))
            if a < before && b > after { item["occurrence_id"] = .string(original); output.append(.object(item)) }
            guard output.count <= 1000 else { throw ConnectFailure.resourceBusy }
        }
        try points(value, through: before) { point in
            let original = key(point, allDay: allDay, zone: zone); seen.insert(original); try include(point, original)
        }
        for (original, patch) in value["exceptions"].object ?? [:] where !seen.contains(original) && patch["start"].string != nil {
            let date = allDay ? try SyncDate.parse(original, dateOnly: true) : try SyncDate.parse(original, zoned: true)
            if let point = allDay ? local(date, zone: zone) : date { try include(point, original) }
        }
        return try output.sorted { try bounds($0).0 < bounds($1).0 }
    }
    static func reminderTimes(_ definition: ConnectJSON, target: ConnectJSON, after: Date, before: Date) throws -> [Date] {
        guard !["completed", "cancelled"].contains(target["status"].string ?? "") else { return [] }
        let offset = Double(definition["offset_minutes"].integer ?? 0) * 60
        var times: [Date] = []
        if let at = definition["at"].string, !at.isEmpty { times = [try SyncDate.parse(at, zoned: true)] }
        else if definition["target_kind"] == .string("event") {
            times = try occurrences(target, after: after.addingTimeInterval(offset), before: before.addingTimeInterval(offset)).map { try bounds($0).0.addingTimeInterval(-offset) }
        } else if let due = target["due"].string, !due.isEmpty {
            if target["due_kind"] == .string("date") {
                let wall = try SyncDate.parse(due, dateOnly: true).addingTimeInterval(9 * 3600)
                guard let zone = TimeZone(identifier: target["timezone"].string ?? ""), let date = local(wall, zone: zone) else { throw ConnectFailure.responseMalformed }
                times = [date.addingTimeInterval(-offset)]
            } else { times = [try SyncDate.parse(due, zoned: true).addingTimeInterval(-offset)] }
        }
        return times.filter { $0 >= after && $0 < before }
    }

}
