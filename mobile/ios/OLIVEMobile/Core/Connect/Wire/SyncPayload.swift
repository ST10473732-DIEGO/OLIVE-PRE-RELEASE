import Foundation

enum SyncPayload {
    static func validate(kind: String, value v: ConnectJSON) throws {
        func text(_ key: String, _ max: Int = 200, required: Bool = false) throws {
            let s = try v[key].text()
            guard s.unicodeScalars.count <= max, !s.contains("\0"), !required || (!s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && s == s.trimmingCharacters(in: .whitespacesAndNewlines)) else { throw ConnectFailure.responseMalformed }
        }
        func choice(_ key: String, _ values: Set<String>) throws { guard values.contains(v[key].string ?? "") else { throw ConnectFailure.responseMalformed } }
        func boolean(_ key: String) throws { guard v[key].boolean != nil else { throw ConnectFailure.responseMalformed } }
        func strings(_ key: String, max: Int = 30) throws {
            guard let values = v[key].array, values.count <= max, Set(values.map(\.digest)).count == values.count else { throw ConnectFailure.responseMalformed }
            for value in values { let s = try value.text(); guard !s.isEmpty, s.unicodeScalars.count <= 200, !s.contains("\0") else { throw ConnectFailure.responseMalformed } }
        }
        func zone() throws { guard let name = v["timezone"].string, name.count <= 100, TimeZone(identifier: name) != nil else { throw ConnectFailure.responseMalformed } }
        switch kind {
        case "task":
            try v.fields(["title", "description", "status", "priority", "due", "due_kind", "timezone", "project_id", "event_id", "agent_task_id", "contact_ids", "completed_at"])
            try text("title", required: true); try text("description", 8000); try text("project_id"); try text("event_id"); try text("completed_at", 80)
            guard v["agent_task_id"] == .string("") else { throw ConnectFailure.responseMalformed }
            try choice("status", ["open", "completed"]); try choice("priority", ["low", "normal", "high"]); try choice("due_kind", ["date", "time"]); try zone(); try strings("contact_ids")
            if v["due"] != .string("") {
                if v["due_kind"] == .string("date") { _ = try SyncDate.parse(v["due"].text(), dateOnly: true) }
                else { _ = try SyncDate.nativeInstant(v["due"].text(), zone: v["timezone"].text()) }
            }
        case "calendar":
            try v.fields(["title", "colour", "visible"]); try text("title", 120, required: true); try boolean("visible")
            guard v["colour"].string?.range(of: "^#[0-9a-fA-F]{6}$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
        case "reminder":
            try v.fields(["target_kind", "target_id", "at", "offset_minutes", "timezone"])
            try choice("target_kind", ["task", "event"]); try text("target_id", 100, required: true); try zone()
            _ = try v["offset_minutes"].number(0...525600)
            if v["at"] != .string("") { try SyncWire.instant(v["at"], requireZone: true); guard v["at"].string!.hasSuffix("+00:00") else { throw ConnectFailure.responseMalformed } }
        case "conversation":
            try v.fields(["title", "project_id", "created_at"])
            guard let title = v["title"].string, title.unicodeScalars.count <= 200 else { throw ConnectFailure.responseMalformed }
            if v["project_id"] != .null { guard let s = v["project_id"].string, s.count <= 100 else { throw ConnectFailure.responseMalformed } }
            try SyncWire.instant(v["created_at"])
        case "message":
            try v.fields(["conversation_id", "after", "role", "content", "created_at"])
            _ = try SyncWire.recordID(v["conversation_id"])
            if v["after"] != .null { _ = try SyncWire.recordID(v["after"]) }
            try choice("role", ["user", "assistant"])
            guard let content = v["content"].string, content.utf8.count <= 64000 else { throw ConnectFailure.responseMalformed }
            try SyncWire.instant(v["created_at"])
        case "event":
            try v.fields(["calendar_id", "title", "description", "location", "start", "end", "timezone", "all_day", "recurrence", "exceptions", "contact_ids", "project_id", "status", "transparent", "unsupported", "original_ics"])
            for key in ["calendar_id", "title", "location", "project_id"] { try text(key, 300, required: ["calendar_id", "title"].contains(key)) }
            try text("description", 8000); try text("original_ics", 32000); try zone(); try boolean("all_day"); try boolean("transparent")
            try choice("status", ["confirmed", "tentative", "cancelled"]); try strings("contact_ids"); try strings("unsupported", max: 100)
            let start: Date, end: Date
            if v["all_day"] == .bool(true) {
                start = try SyncDate.parse(v["start"].text(), dateOnly: true); end = try SyncDate.parse(v["end"].text(), dateOnly: true)
            } else {
                start = try SyncDate.nativeInstant(v["start"].text(), zone: v["timezone"].text())
                end = try SyncDate.nativeInstant(v["end"].text(), zone: v["timezone"].text())
            }
            guard end > start, end.timeIntervalSince(start) < 367 * 86400 else { throw ConnectFailure.responseMalformed }
            try text("recurrence", 500)
            if v["recurrence"] != .string("") {
                var fields: [String: String] = [:]
                for field in v["recurrence"].string!.split(separator: ";") {
                    let pair = field.split(separator: "=", maxSplits: 1)
                    guard pair.count == 2, fields[String(pair[0])] == nil, ["FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "BYMONTH", "COUNT", "UNTIL", "WKST"].contains(String(pair[0])) else { throw ConnectFailure.responseMalformed }
                    fields[String(pair[0])] = String(pair[1])
                }
                guard ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"].contains(fields["FREQ"] ?? ""), fields["COUNT"] == nil || fields["UNTIL"] == nil else { throw ConnectFailure.responseMalformed }
                for (key, max) in [("INTERVAL", 366), ("COUNT", 10000)] {
                    if let raw = fields[key] { guard let n = Int(raw), (1...max).contains(n) else { throw ConnectFailure.responseMalformed } }
                }
                for (key, min, max) in [("BYMONTHDAY", -31, 31), ("BYMONTH", 1, 12)] {
                    if let raw = fields[key] { for part in raw.split(separator: ",", omittingEmptySubsequences: false) { guard let n = Int(part), n != 0, (min...max).contains(n) else { throw ConnectFailure.responseMalformed } } }
                }
                if let raw = fields["BYDAY"] { for part in raw.split(separator: ",", omittingEmptySubsequences: false) {
                    guard String(part).range(of: #"^([+-]?[1-9][0-9]?)?(MO|TU|WE|TH|FR|SA|SU)$"#, options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
                } }
                if let raw = fields["WKST"], !["MO", "TU", "WE", "TH", "FR", "SA", "SU"].contains(raw) { throw ConnectFailure.responseMalformed }
                if let raw = fields["UNTIL"], raw.range(of: #"^\d{8}(T\d{6}Z?)?$"#, options: .regularExpression) == nil { throw ConnectFailure.responseMalformed }
            }
            guard let exceptions = v["exceptions"].object, exceptions.count <= 500 else { throw ConnectFailure.responseMalformed }
            for (date, patch) in exceptions {
                try SyncWire.instant(.string(date))
                guard let fields = patch.object, Set(fields.keys).isSubset(of: ["start", "end", "title", "location", "description", "cancelled"]), (fields["start"] == nil) == (fields["end"] == nil) else { throw ConnectFailure.responseMalformed }
                for (key, value) in fields {
                    if key == "cancelled" { guard value.boolean != nil else { throw ConnectFailure.responseMalformed } }
                    else { _ = try StudioWire.bounded(value, key == "description" ? 32000 : 1200) }
                }
            }
        default: throw ConnectFailure.responseMalformed
        }
    }
    static func task(title: String) -> ConnectJSON {
        .object(["title": .string(title), "description": .string(""), "status": .string("open"), "priority": .string("normal"),
            "due": .string(""), "due_kind": .string("date"), "timezone": .string(TimeZone.current.identifier),
            "project_id": .string(""), "event_id": .string(""), "agent_task_id": .string(""), "contact_ids": .array([]), "completed_at": .string("")])
    }
}
