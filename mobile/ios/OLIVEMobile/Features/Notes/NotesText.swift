import Foundation

/// UTF-16 text rules for the phone editor. NSString/UITextView ranges and the
/// Yjs engine both count UTF-16 code units, so ranges pass through unchanged.
/// Mirrors desktop/src/features/notes/engine/text.ts (textDiff/transformIndex).
enum NotesText {
    struct Change: Equatable { let index: Int; let remove: Int; let insert: String }

    private static func high(_ unit: UInt16) -> Bool { (0xD800...0xDBFF).contains(unit) }
    private static func low(_ unit: UInt16) -> Bool { (0xDC00...0xDFFF).contains(unit) }

    /// Minimal single replacement turning `before` into `after`, never splitting a surrogate pair.
    static func diff(_ before: String, _ after: String) -> Change? {
        let a = Array(before.utf16), b = Array(after.utf16)
        if a == b { return nil }
        let limit = min(a.count, b.count)
        var start = 0
        while start < limit && a[start] == b[start] { start += 1 }
        if start > 0 && high(a[start - 1]) && ((start < a.count && low(a[start])) || (start < b.count && low(b[start]))) { start -= 1 }
        var end = 0
        while end < limit - start && a[a.count - 1 - end] == b[b.count - 1 - end] { end += 1 }
        if end > 0 {
            let x = a.count - end, y = b.count - end
            if (x - 1 >= start && low(a[x]) && high(a[x - 1])) || (y - 1 >= start && low(b[y]) && high(b[y - 1])) { end -= 1 }
        }
        let inserted = String(decoding: b[start..<(b.count - end)], as: UTF16.self)
        return Change(index: start, remove: a.count - start - end, insert: inserted)
    }

    /// Where a caret at `index` lands after a Yjs delta (retain/insert/delete).
    static func transform(_ index: Int, _ delta: [ConnectJSON]) -> Int {
        var position = 0, result = index
        for op in delta {
            if let retain = op["retain"].integer { position += Int(retain) }
            else if let insert = op["insert"].string {
                let size = insert.utf16.count
                if position < result { result += size }
                position += size
            } else if let remove = op["delete"].integer {
                let end = position + Int(remove)
                if end <= result { result -= Int(remove) } else if position < result { result = position }
            }
        }
        return result
    }

    /// The rename a title field asks for, or nil. `baseline` is the stored title
    /// the field last showed; a field the user did not edit never writes, so a
    /// rename that synced in while the editor was open is not reverted.
    static func titleChange(field: String, baseline: String) -> String? {
        let title = field.trimmingCharacters(in: .whitespacesAndNewlines)
        return title == baseline ? nil : title
    }

    static func normalize(_ text: String) -> String {
        text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n").replacingOccurrences(of: "\0", with: "")
    }
}
