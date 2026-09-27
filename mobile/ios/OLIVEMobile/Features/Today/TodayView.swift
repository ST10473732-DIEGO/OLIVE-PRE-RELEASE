import SwiftUI

struct TodayView: View {
    @Environment(AppState.self) private var state
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var recovering = false
    private let domains: [(String, String)] = [("tasks", "checklist"), ("calendar", "calendar"), ("reminders", "bell")]
    var body: some View {
        let model = state.sync
        List {
            Section {
                HStack(spacing: 10) {
                    StatusDot(color: model.online ? OliveTheme.accent : OliveTheme.muted, pulsing: model.busy)
                    Text(model.online ? "Connected · changes sync when you request them" : "Offline · saved records are read-only")
                        .font(.subheadline).foregroundStyle(OliveTheme.secondary)
                }
                if !model.notice.isEmpty || model.busy {
                    HStack(spacing: 10) {
                        if model.busy { ProgressView().controlSize(.small).tint(OliveTheme.accent) }
                        Text(model.notice).font(.subheadline).accessibilityIdentifier("today.status")
                    }
                }
                if model.busy {
                    Button("Cancel sync", role: .destructive) { model.cancel() }
                }
                if !model.store.available {
                    Button("Recover local sync storage") { recovering = true }
                        .foregroundStyle(OliveTheme.attention).accessibilityIdentifier("today.recover")
                }
                NavigationLink { TodayAgendaView() } label: {
                    TodayRowLabel(symbol: "calendar.day.timeline.left", tint: OliveTheme.accent, title: "Agenda", detail: "What’s due, day by day")
                }
            }.listRowBackground(OliveTheme.raised)
            ForEach(domains, id: \.0) { domain, symbol in
                Section {
                    let records = model.records.filter { !$0.deleted && SyncWire.domains[$0.kind] == domain }
                    if records.isEmpty {
                        Text("Nothing here yet").font(.subheadline).foregroundStyle(OliveTheme.muted)
                    }
                    ForEach(records) { record in
                        NavigationLink {
                            TodayEditor(kind: record.kind, old: record)
                        } label: {
                            TodayRowLabel(symbol: icon(record), tint: tint(record), title: record.payload["title"].string ?? reminderTitle(record),
                                          detail: detail(record), warning: model.recordState(record))
                        }
                    }
                    ForEach(newKinds(domain), id: \.self) { kind in
                        NavigationLink { TodayEditor(kind: kind) } label: {
                            Label("New " + kind, systemImage: "plus.circle.fill").foregroundStyle(OliveTheme.accent)
                        }
                    }
                } header: {
                    HStack(alignment: .center) {
                        Label(domain.capitalized, systemImage: symbol).font(.footnote.weight(.semibold))
                        Spacer()
                        Button { Task { await model.sync(domain) } } label: {
                            Label("Sync", systemImage: "arrow.triangle.2.circlepath").font(.caption.weight(.semibold))
                                .padding(.horizontal, 10).padding(.vertical, 5)
                                .background(OliveTheme.accent.opacity(0.12), in: Capsule())
                        }
                        .foregroundStyle(OliveTheme.accent).opacity(!model.online || model.busy ? 0.4 : 1).disabled(!model.online || model.busy)
                        .accessibilityLabel("Sync \(domain)")
                    }
                } footer: {
                    if let status = model.domainStatus[domain] { Text(status) }
                }.listRowBackground(OliveTheme.raised)
            }
            if !model.conflicts.isEmpty {
                Section("Conflicts") {
                    ForEach(model.conflicts) { conflict in
                        NavigationLink { SyncConflictView(conflict: conflict) } label: {
                            TodayRowLabel(symbol: "exclamationmark.triangle", tint: OliveTheme.attention,
                                          title: "Review " + conflict.reason, detail: "Choose which version to keep")
                        }.accessibilityIdentifier("today.conflict")
                    }
                }.listRowBackground(OliveTheme.attention.opacity(0.12))
            }
        }
        .listStyle(.insetGrouped).listRowSeparatorTint(OliveTheme.border).oliveListStyle()
        .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.records.count)
        .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.busy)
        .navigationTitle("Today").navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Preserve and rebuild local sync storage?", isPresented: $recovering, titleVisibility: .visible) {
                Button("Preserve data and rebuild") { model.recoverLocalSync() }
            } message: {
                Text("The unreadable file stays in protected recovery storage. This starts an empty sync store; use explicit Sync to retrieve desktop records. Unsynced edits remain only in the preserved file and are not automatically replayed. Drafts and pairing stay intact.")
            }
    }
    private func newKinds(_ domain: String) -> [String] {
        domain == "tasks" ? ["task"] : domain == "calendar" ? ["calendar", "event"] : ["reminder"]
    }
    private func icon(_ record: SignedSyncRecord) -> String {
        switch record.kind {
        case "task": record.payload["status"] == .string("completed") ? "checkmark.circle.fill" : "circle"
        case "event": "clock"
        case "reminder": "bell"
        default: "square.stack"
        }
    }
    private func tint(_ record: SignedSyncRecord) -> Color {
        if record.kind == "calendar", let colour = Color(oliveHex: record.payload["colour"].string ?? "") { return colour }
        return record.kind == "task" && record.payload["status"] != .string("completed") ? OliveTheme.secondary : OliveTheme.accent
    }
    private func detail(_ record: SignedSyncRecord) -> String {
        let p = record.payload
        switch record.kind {
        case "task":
            if p["status"] == .string("completed") { return "Completed" }
            if let due = p["due"].string, !due.isEmpty { return "Due " + TodayFormat.pretty(due) }
            return "Open"
        case "event": return TodayFormat.pretty(p["start"].string ?? "")
        case "reminder": return p["at"].string.map { $0.isEmpty ? "Linked schedule" : TodayFormat.pretty($0) } ?? "Linked schedule"
        default: return "Calendar"
        }
    }
    private func reminderTitle(_ record: SignedSyncRecord) -> String {
        state.sync.records.first { $0.id == record.payload["target_id"].string }?.payload["title"].string.map { "Reminder · " + $0 } ?? "Reminder"
    }
}

/// Icon, title and subtitle for Today rows; texts stay separate for VoiceOver and UI tests.
private struct TodayRowLabel: View {
    let symbol: String
    var tint: Color = OliveTheme.accent
    let title: String
    var detail: String = ""
    var warning: String? = nil
    var body: some View {
        HStack(spacing: 12) {
            OliveIcon(symbol: symbol, size: 32, tint: tint)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body).foregroundStyle(OliveTheme.text)
                if let warning { Text(warning).font(.caption).foregroundStyle(OliveTheme.attention) }
                if !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(OliveTheme.muted) }
            }
        }.padding(.vertical, 2)
    }
}

enum TodayFormat {
    /// Friendly date for stored ISO strings; unknown formats are shown unchanged.
    static func pretty(_ raw: String) -> String {
        let full = ISO8601DateFormatter()
        if let date = full.date(from: raw) { return date.formatted(date: .abbreviated, time: .shortened) }
        full.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = full.date(from: raw) { return date.formatted(date: .abbreviated, time: .shortened) }
        full.formatOptions = [.withFullDate]; full.timeZone = .current
        if let date = full.date(from: raw) { return date.formatted(date: .abbreviated, time: .omitted) }
        return raw
    }
}

extension Color {
    init?(oliveHex: String) {
        let hex = oliveHex.hasPrefix("#") ? String(oliveHex.dropFirst()) : oliveHex
        guard hex.count == 6, let value = UInt32(hex, radix: 16) else { return nil }
        self.init(.sRGB, red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
    }
}

struct TodayEditor: View {
    @Environment(AppState.self) private var state
    let kind: String
    var old: SignedSyncRecord?
    @State private var fields: [String: ConnectJSON] = [:]
    @State private var notice = ""
    @State private var deleting = false
    @State private var saving = false
    @State private var current: SignedSyncRecord?
    @State private var loaded = false
    @State private var draftKey = ""
    private func persistDraft() {
        guard loaded else { return }
        do { try state.sync.store.drafts.save(draftKey, original: current, fields: current?.payload.object == fields ? nil : fields) }
        catch { notice = "Draft could not be saved. Keep this editor open to retain your text." }
    }
    private func text(_ key: String) -> Binding<String> { Binding(get: { fields[key]?.string ?? "" }, set: { fields[key] = .string($0) }) }
    var body: some View {
        Form {
            Section {
            if kind == "task" || kind == "calendar" || kind == "event" { TextField("Title", text: text("title")) }
            if kind == "task" || kind == "event" { TextField("Description", text: text("description"), axis: .vertical) }
            if kind == "task" {
                Toggle("Completed", isOn: Binding(get: { fields["status"] == .string("completed") }, set: {
                    fields["status"] = .string($0 ? "completed" : "open"); fields["completed_at"] = .string($0 ? SyncWire.now() : "")
                }))
                TextField("Due (YYYY-MM-DD or full timestamp)", text: text("due"))
                Picker("Due kind", selection: text("due_kind")) { Text("Date").tag("date"); Text("Time").tag("time") }
                Picker("Priority", selection: text("priority")) { ForEach(["low", "normal", "high"], id: \.self) { Text($0.capitalized).tag($0) } }
            }
            if kind == "event" {
                Picker("Calendar", selection: text("calendar_id")) {
                    Text("Choose calendar").tag("")
                    ForEach(state.sync.records.filter { $0.kind == "calendar" && !$0.deleted }) { Text($0.payload["title"].string ?? "Calendar").tag($0.id) }
                }
                Toggle("All day", isOn: Binding(get: { fields["all_day"] == .bool(true) }, set: { fields["all_day"] = .bool($0) }))
                TextField("Start (ISO date/time)", text: text("start"))
                TextField("End (exclusive for all-day events)", text: text("end"))
                TextField("Location", text: text("location"))
                Text("Recurrence and exceptions are preserved. Advanced recurrence editing remains on your computer.").font(.footnote)
            }
            if kind == "reminder" {
                Picker("Linked task or event", selection: text("target_id")) {
                    Text("Choose target").tag("")
                    ForEach(state.sync.records.filter { ["task", "event"].contains($0.kind) && !$0.deleted }) { Text($0.payload["title"].string ?? "Record").tag($0.id) }
                }.onChange(of: fields["target_id"]?.string) { _, id in
                    if let target = state.sync.records.first(where: { $0.id == id }) { fields["target_kind"] = .string(target.kind) }
                }
                TextField("Reminder time (UTC ISO timestamp)", text: text("at"))
                Text("Completion follows the linked task.").font(.footnote)
            }
            if kind != "calendar" { TextField("IANA timezone", text: text("timezone")) }
            } header: { Text("Details") }.listRowBackground(OliveTheme.raised)
            Section {
            Button {
                saving = true
                Task {
                    do {
                        current = try await state.sync.save(kind: kind, payload: .object(fields), old: current)
                        try state.sync.store.drafts.save(draftKey, original: nil, fields: nil)
                        notice = "Saved · tap Sync to commit to computer"
                    } catch { notice = error.localizedDescription }
                    saving = false
                }
            } label: {
                HStack { Spacer(); if saving { ProgressView().tint(OliveTheme.accentInk) }; Text("Save locally").font(.headline); Spacer() }
                    .foregroundStyle(OliveTheme.accentInk)
            }.disabled(!state.sync.online || state.sync.busy || saving)
                .listRowBackground(OliveTheme.accent.opacity(!state.sync.online || state.sync.busy || saving ? 0.4 : 1))
            Button {
                notice = "" // A saved-draft notice must not hide the exchange result.
                Task { await state.sync.sync(SyncWire.domains[kind] ?? kind) }
            } label: {
                Label("Sync \(SyncWire.domains[kind] ?? kind)", systemImage: "arrow.triangle.2.circlepath").frame(maxWidth: .infinity)
            }
                .disabled(!state.sync.online || state.sync.busy || saving).listRowBackground(OliveTheme.raised)
            } footer: {
                let message = notice.isEmpty ? state.sync.notice : notice
                if !message.isEmpty { Text(message).font(.footnote).foregroundStyle(OliveTheme.secondary) }
            }
            let conflicts = state.sync.conflicts.filter { $0.recordID == current?.id }
            if !conflicts.isEmpty {
                Section {
                    ForEach(conflicts) { conflict in
                        NavigationLink { SyncConflictView(conflict: conflict) } label: {
                            Label("Review conflict", systemImage: "exclamationmark.triangle").foregroundStyle(OliveTheme.attention)
                        }.accessibilityIdentifier("today.editorConflict")
                    }
                }.listRowBackground(OliveTheme.attention.opacity(0.12))
            }
            if current != nil {
                Section {
                    Button("Delete", role: .destructive) { deleting = true }.frame(maxWidth: .infinity)
                        .disabled(!state.sync.online || saving || state.sync.busy)
                }.listRowBackground(OliveTheme.raised)
            }
        }.oliveListStyle().navigationTitle(kind.capitalized).navigationBarTitleDisplayMode(.inline)
            .onAppear {
                guard !loaded else { return }
                draftKey = (state.session?.selectedID ?? "local") + ":" + (old?.id ?? "new-" + kind)
                current = old; fields = old?.payload.object ?? defaults()
                do {
                    if let draft = try state.sync.store.drafts.get(draftKey) {
                        current = draft.original
                        fields = try ConnectJSON.decode(draft.fields, limit: 72000).object ?? fields
                        notice = "Restored unsaved draft · reconnect to save"
                        if current?.revision != old?.revision { notice = "The saved record changed. Your draft is preserved; saving will refuse a stale revision." }
                    }
                } catch { notice = "Saved draft unavailable; existing data preserved." }
                loaded = true
            }
            .onChange(of: state.sync.records.first(where: { $0.id == current?.id })?.revision) { _, _ in
                guard let updated = state.sync.records.first(where: { $0.id == current?.id }), updated.revision != current?.revision else { return }
                if fields == current?.payload.object {
                    current = updated; fields = updated.payload.object ?? [:]; notice = updated.deleted ? "Deleted record" : "Updated from sync"
                } else { notice = "This record changed. Your draft is preserved; saving will refuse a stale revision." }
            }
            .onChange(of: fields) { _, _ in persistDraft() }
            .onDisappear { persistDraft() }
            .confirmationDialog("Delete this record? A tombstone will sync when requested.", isPresented: $deleting) {
                Button("Delete", role: .destructive) { Task {
                    do { current = try await state.sync.save(kind: kind, payload: .object([:]), old: current, deleted: true); fields = [:]; notice = "Deleted locally · sync pending" }
                    catch { notice = error.localizedDescription }
                } }
            }
    }
    private func defaults() -> [String: ConnectJSON] {
        if kind == "task" { return SyncPayload.task(title: "").object! }
        if kind == "calendar" { return ["title": .string(""), "colour": .string("#5b9bff"), "visible": .bool(true)] }
        if kind == "reminder" { return ["target_kind": .string("task"), "target_id": .string(""), "at": .string(""), "offset_minutes": .int(30), "timezone": .string("UTC")] }
        let start = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: "Z", with: "+00:00")
        let end = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600)).replacingOccurrences(of: "Z", with: "+00:00")
        return ["calendar_id": .string(""), "title": .string(""), "description": .string(""), "location": .string(""), "project_id": .string(""),
            "timezone": .string("UTC"), "all_day": .bool(false), "status": .string("confirmed"), "transparent": .bool(false),
            "contact_ids": .array([]), "unsupported": .array([]), "original_ics": .string(""), "start": .string(start), "end": .string(end),
            "recurrence": .string(""), "exceptions": .object([:])]
    }
}


private struct SyncConflictView: View {
    @Environment(AppState.self) private var state
    let conflict: SyncConflict
    @State private var reviewed: SyncConflict?
    @State private var local: SignedSyncRecord?
    private func summary(_ record: SignedSyncRecord?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let record {
                if record.deleted { Text("Deleted record") }
                else {
                    ForEach(["title", "description", "status", "due", "start", "end", "at", "content", "target_kind", "target_id"], id: \.self) { key in
                        if let text = record.payload[key].string, !text.isEmpty {
                            Text(key.replacingOccurrences(of: "_", with: " ").capitalized).font(.caption).foregroundStyle(OliveTheme.secondary)
                            Text(text).textSelection(.enabled)
                        }
                    }
                }
            } else { Text("No local version") }
        }
    }
    var body: some View {
        List {
            Section {
                Label(conflict.reason.replacingOccurrences(of: "_", with: " ").capitalized, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(OliveTheme.attention)
            }.listRowBackground(OliveTheme.attention.opacity(0.12))
            Section { summary(local) } header: { Label("This iPhone", systemImage: "iphone") }.listRowBackground(OliveTheme.raised)
            Section { summary(conflict.incoming) } header: { Label("Incoming", systemImage: "desktopcomputer") }.listRowBackground(OliveTheme.raised)
            Section {
                Button("Keep this iPhone’s version") { if let reviewed { Task { await state.sync.resolve(reviewed, incoming: false) } } }
                    .disabled(local == nil)
                Button("Use incoming version") { if let reviewed { Task { await state.sync.resolve(reviewed, incoming: true) } } }
            } footer: {
                if !state.sync.notice.isEmpty { Text(state.sync.notice) }
            }.disabled(!state.sync.online || state.sync.busy).listRowBackground(OliveTheme.raised)
        }.oliveListStyle().navigationTitle("Review conflict").navigationBarTitleDisplayMode(.inline)
            .onAppear {
                local = state.sync.store.snapshot.records[conflict.recordID]
                reviewed = SyncConflict(id: conflict.id, peer: conflict.peer, recordID: conflict.recordID,
                    localRevision: local?.revision, incoming: conflict.incoming, reason: conflict.reason)
            }
    }
}


private struct TodayAgendaItem: Identifiable, Sendable {
    let id: String
    let record: SignedSyncRecord
    let title: String
    let detail: String
    let time: Date
}
private struct TodayAgendaView: View {
    @Environment(AppState.self) private var state
    @State private var day = Date()
    @State private var items: [TodayAgendaItem] = []
    @State private var notice = ""
    var body: some View {
        List {
            Section {
                DatePicker("Day", selection: $day, displayedComponents: .date).tint(OliveTheme.accent)
            } footer: { Text("Saved OLIVE records · Sync in Today to refresh") }.listRowBackground(OliveTheme.raised)
            Section {
                ForEach(items) { item in
                    NavigationLink { TodayEditor(kind: item.record.kind, old: item.record) } label: {
                        HStack(spacing: 14) {
                            Text(item.detail).font(.caption.weight(.semibold).monospacedDigit())
                                .foregroundStyle(item.detail == "Overdue" ? OliveTheme.attention : OliveTheme.accent)
                                .frame(width: 76, alignment: .leading)
                            Rectangle().fill(OliveTheme.border).frame(width: 1).padding(.vertical, 2)
                            Text(item.title).font(.body)
                        }
                    }
                }
                if !notice.isEmpty { Text(notice).font(.subheadline).foregroundStyle(OliveTheme.muted) }
            }.listRowBackground(OliveTheme.raised)
        }.oliveListStyle().animation(OliveTheme.Motion.settle, value: items.map(\.id))
            .navigationTitle("Agenda").navigationBarTitleDisplayMode(.inline)
            .task(id: day) { await refresh() }
    }
    private func refresh() async {
        let records = state.sync.records, start = Calendar.current.startOfDay(for: day)
        guard let end = Calendar.current.date(byAdding: .day, value: 1, to: start) else { return }
        notice = "Loading saved records…"
        let work = Task.detached { () throws -> [TodayAgendaItem] in
            var result: [TodayAgendaItem] = []
            let byID = Dictionary(uniqueKeysWithValues: records.map { ($0.id, $0) })
            for record in records where !record.deleted {
                try Task.checkCancellation()
                let p = record.payload
                if record.kind == "event" {
                    for occurrence in try SyncCalendar.occurrences(p, after: start, before: end) {
                        let (time, _, _, allDay) = try SyncCalendar.bounds(occurrence)
                        result.append(TodayAgendaItem(id: record.id + ":" + (occurrence["occurrence_id"].string ?? ""), record: record,
                            title: occurrence["title"].string ?? "Event", detail: allDay ? "All day" : time.formatted(date: .omitted, time: .shortened), time: time))
                    }
                } else if record.kind == "task", p["status"] != .string("completed"), let due = p["due"].string, !due.isEmpty {
                    let dateOnly = p["due_kind"] == .string("date")
                    let raw = try SyncDate.parse(due, zoned: !dateOnly, dateOnly: dateOnly)
                    let time = dateOnly ? SyncCalendar.local(raw, zone: TimeZone(identifier: p["timezone"].string ?? "UTC")!) ?? raw : raw
                    if time < end {
                        result.append(TodayAgendaItem(id: record.id, record: record, title: p["title"].string ?? "Task",
                            detail: time < start ? "Overdue" : dateOnly ? "Due today" : "Due " + time.formatted(date: .omitted, time: .shortened), time: time))
                    }
                } else if record.kind == "reminder", let target = byID[p["target_id"].string ?? ""], !target.deleted, target.payload["status"] != .string("completed") {
                    for time in try SyncCalendar.reminderTimes(p, target: target.payload, after: start, before: end) {
                        result.append(TodayAgendaItem(id: record.id + ":" + String(time.timeIntervalSince1970), record: record, title: "Reminder · " + (target.payload["title"].string ?? "OLIVE"),
                            detail: time.formatted(date: .omitted, time: .shortened), time: time))
                    }
                }
                guard result.count <= 1000 else { throw ConnectFailure.resourceBusy }
            }
            return result.sorted { $0.time == $1.time ? $0.id < $1.id : $0.time < $1.time }
        }
        do {
            let result = try await withTaskCancellationHandler { try await work.value } onCancel: { work.cancel() }
            guard !Task.isCancelled else { return }; items = result; notice = result.isEmpty ? "No due items for this day." : ""
        } catch {
            guard !Task.isCancelled else { return }; items = []; notice = "This agenda could not be expanded safely. Your saved records remain available in Today."
        }
    }
}
