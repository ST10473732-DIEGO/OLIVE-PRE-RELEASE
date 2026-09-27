import SwiftUI

struct TodayView: View {
    @Environment(AppState.self) private var state
    var body: some View {
        let model = state.sync
        List {
            Section {
                Text(model.online ? "Connected · changes sync when you request them" : "Offline · saved records are read-only")
                Text(model.notice).accessibilityIdentifier("today.status")
                if model.busy { Button("Cancel sync") { model.cancel() } }
            }
            ForEach(["tasks", "calendar", "reminders"], id: \.self) { domain in
                Section(domain.capitalized) {
                    Button("Sync \(domain)") { Task { await model.sync(domain) } }.disabled(!model.online || model.busy)
                    if let status = model.domainStatus[domain] { Text(status).font(.caption) }
                    ForEach(model.records.filter { !$0.deleted && SyncWire.domains[$0.kind] == domain }) { record in
                        NavigationLink {
                            TodayEditor(kind: record.kind, old: record)
                        } label: {
                            VStack(alignment: .leading) {
                                Text(record.payload["title"].string ?? reminderTitle(record)).font(.headline)
                                Text(record.kind == "task" ? record.payload["status"].string ?? "" : record.kind == "event" ? record.payload["start"].string ?? "" : record.kind == "reminder" ? record.payload["at"].string ?? "Linked schedule" : "Calendar")
                                    .font(.caption).foregroundStyle(OliveTheme.secondary)
                            }
                        }
                    }
                    if domain == "tasks" { NavigationLink("New task") { TodayEditor(kind: "task") } }
                    if domain == "calendar" {
                        NavigationLink("New calendar") { TodayEditor(kind: "calendar") }
                        NavigationLink("New event") { TodayEditor(kind: "event") }
                    }
                    if domain == "reminders" { NavigationLink("New reminder") { TodayEditor(kind: "reminder") } }
                }
            }
            if !model.conflicts.isEmpty {
                Section("Conflicts") {
                    ForEach(model.conflicts) { conflict in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(conflict.reason).font(.headline)
                            Text("This iPhone: " + (model.store.snapshot.records[conflict.recordID]?.payload["title"].string ?? "Record or tombstone"))
                            Text("Incoming: " + (conflict.incoming.payload["title"].string ?? "Record or tombstone"))
                            Button("Keep this iPhone’s version") { Task { await model.resolve(conflict, incoming: false) } }
                            Button("Use incoming version") { Task { await model.resolve(conflict, incoming: true) } }
                        }.disabled(!model.online || model.busy).accessibilityIdentifier("today.conflict")
                    }
                }
            }
        }.navigationTitle("Today")
    }
    private func reminderTitle(_ record: SignedSyncRecord) -> String {
        state.sync.records.first { $0.id == record.payload["target_id"].string }?.payload["title"].string.map { "Reminder · " + $0 } ?? "Reminder"
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
    private func text(_ key: String) -> Binding<String> { Binding(get: { fields[key]?.string ?? "" }, set: { fields[key] = .string($0) }) }
    var body: some View {
        Form {
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
                Text("Completion follows the linked task. Notification delivery is local to each device.").font(.footnote)
            }
            if kind != "calendar" { TextField("IANA timezone", text: text("timezone")) }
            Button("Save locally") {
                saving = true
                Task {
                    do {
                        try await state.sync.save(kind: kind, payload: .object(fields), old: current)
                        current = state.sync.records.last { $0.kind == kind && $0.payload == .object(fields) }
                        notice = "Saved · tap Sync to commit to computer"
                    } catch { notice = error.localizedDescription }
                    saving = false
                }
            }.disabled(!state.sync.online || state.sync.busy || saving)
            Button("Sync \(SyncWire.domains[kind] ?? kind)") { Task { await state.sync.sync(SyncWire.domains[kind] ?? kind) } }
                .disabled(!state.sync.online || state.sync.busy || saving)
            if current != nil { Button("Delete", role: .destructive) { deleting = true }.disabled(!state.sync.online || saving || state.sync.busy) }
            Text(notice.isEmpty ? state.sync.notice : notice)
        }.navigationTitle(kind.capitalized)
            .onAppear { if fields.isEmpty { current = old; fields = old?.payload.object ?? defaults() } }
            .confirmationDialog("Delete this record? A tombstone will sync when requested.", isPresented: $deleting) {
                Button("Delete", role: .destructive) { Task {
                    do { try await state.sync.save(kind: kind, payload: .object([:]), old: current, deleted: true); notice = "Deleted locally · sync pending" }
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
