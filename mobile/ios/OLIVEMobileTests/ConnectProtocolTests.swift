import XCTest
import CryptoKit
import Network
@testable import OLIVEMobile

final class RealFileBackgroundPreparationTests: XCTestCase {
    @MainActor func testPrepareOwned64MiBSelection() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_FILE_PREPARE_ACCEPTANCE"] == "1", "Explicit synthetic fixture staging only; no transfer starts here")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let journal = ProtectedStore<[BackgroundOperationRecord]>(url: URL.applicationSupportDirectory.appendingPathComponent("Companion/operations-v1.json"), maximumBytes: 256000)
        guard !(try journal.load() ?? []).contains(where: { $0.state == .running }) else { throw XCTSkip("Do not disturb existing work") }
        let token = UUID().uuidString.lowercased()
        let directory = URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/FileBackground/" + token)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var protected = directory; var values = URLResourceValues(); values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
        let source = directory.appendingPathComponent("olive-c93-64MiB.bin")
        XCTAssertTrue(FileManager.default.createFile(atPath: source.path, contents: nil,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]))
        let handle = try FileHandle(forWritingTo: source)
        let block = Data((0..<1048576).map { UInt8(truncatingIfNeeded: $0) })
        for _ in 0..<64 { try handle.write(contentsOf: block) }
        try handle.close()
        let checked = try FileStaging(directory: directory).digest(source)
        XCTAssertEqual(checked.0, 67108864)
        XCTAssertEqual(checked.1, "281e519df3077b557c6b03f5da83c4e8d397219259615dd7c3308f89cae8f2a6")
        print("C93 OWNED FILE READY \(token)")
    }
}

/// Opt-in, physical-device acceptance against the already paired desktop. No
/// permission changes, profile exports, private records or alternate server.
final class RealCompanionEdgeTests: XCTestCase {
    @MainActor func testRealFileIntegrityAndDisconnectedPeer() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_EDGE_ACCEPTANCE"] == "1", "Explicit real iPhone/CachyOS acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let peer = try XCTUnwrap(ConnectTrustRepository().peers.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let discovery = ConnectDiscoveryService(); discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var connected: ConnectTransport?
        for candidate in discovery.nearby.prefix(8) {
            let candidateChannel = ConnectTransport(endpoint: candidate.endpoint)
            do { try await candidateChannel.connect(identity: identity, peer: peer.identity); connected = candidateChannel; break }
            catch { await candidateChannel.close() }
        }
        let channel = try XCTUnwrap(connected, "Real paired desktop must be reachable")
        let source = identity.publicIdentity.deviceID
        let transfer = UUID().uuidString.lowercased()
        func request(_ operation: String, _ arguments: ConnectJSON = .object([:])) -> ConnectJSON {
            FileWire.request(source: source, target: peer.id, transfer: transfer, operation: operation, arguments: arguments)
        }
        func exchange(_ request: ConnectJSON, bytes: Data = Data()) async throws -> ConnectJSON {
            try ConnectJSON.decode(await channel.exchangeFrame(kind: 7, id: request["request_id"].uuid(), payload: FileWire.packet(request, bytes: bytes)))
        }
        do {
            let capabilities = try await channel.exchange(InferenceWire.request(source: source, target: peer.id, operation: "capabilities"))
            guard capabilities["result"]["permissions"]["files.receive"] == .string("allow") else {
                await channel.close()
                throw XCTSkip("Receive files must already be Allow; acceptance never changes desktop policy")
            }
            // The advertised hash describes different owned bytes. The remote
            // complete must reject them and preserve a failed durable receipt.
            let metadata = try FileMetadata(name: "C93-Acceptance-invalid-hash.bin", size: 4,
                sha256: Data(SHA256.hash(data: Data("good".utf8))).hex, mime: "application/octet-stream")
            let offered = try await exchange(request("offer", metadata.wire))
            XCTAssertEqual(offered["result"]["state"], .string("accepted"))
            guard offered["result"]["state"] == .string("accepted") else { throw ConnectFailure.remotePermissionDenied }
            let chunk = try await exchange(request("chunk", .object(["offset": .int(0)])), bytes: Data("evil".utf8))
            XCTAssertEqual(chunk["result"]["received_size"], .int(4))
            let completed = try await exchange(request("complete"))
            XCTAssertEqual(completed["error"], .string("content_integrity_failed"))
            let status = try await exchange(request("status"))
            XCTAssertEqual(status["result"]["state"], .string("failed"))
            let repeated = try await exchange(request("complete"))
            XCTAssertEqual(repeated["result"]["state"], .string("failed"))
            print("C93 REAL invalid-hash transfer=\(transfer) rejected; durable failed receipt; repeated complete remains failed")

            // The production picker/codec rejects >64 MiB before sending bytes.
            XCTAssertThrowsError(try FileMetadata(name: "C93-Acceptance-oversize.bin", size: FileWire.maximumFile + 1,
                sha256: metadata.sha256, mime: metadata.mime)) { XCTAssertEqual($0 as? ConnectFailure, .fileTooLarge) }
            await channel.close()
            do {
                _ = try await exchange(request("offer", metadata.wire))
                XCTFail("Closed peer must not queue an operation")
            } catch { XCTAssertEqual(error as? ConnectFailure, .peerOffline) }
            print("C93 REAL oversize rejected locally before transfer; closed-session send rejected peerOffline")
        } catch {
            // Best-effort cancellation is scoped to this synthetic transfer only.
            _ = try? await exchange(request("cancel"))
            await channel.close()
            throw error
        }
    }
}

final class RealStudioAcceptanceTests: XCTestCase {
    @MainActor func testOwnedSharedWorkspace() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_EDGE_ACCEPTANCE"] == "1", "Explicit real iPhone/CachyOS acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let peer = try XCTUnwrap(ConnectTrustRepository().peers.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let discovery = ConnectDiscoveryService(); discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var connection: ConnectTransport?
        for candidate in discovery.nearby.prefix(8) {
            let channel = ConnectTransport(endpoint: candidate.endpoint)
            do { try await channel.connect(identity: identity, peer: peer.identity); connection = channel; break }
            catch { await channel.close() }
        }
        let channel = try XCTUnwrap(connection, "Real paired desktop must be reachable")
        func exchange(_ request: ConnectJSON) async throws -> ConnectJSON {
            try StudioWire.response(await channel.exchangeFrame(kind: 11, id: request["request_id"].uuid(), payload: request.canonical), request: request)
        }
        do {
            let list = try await exchange(StudioWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: "workspaces"))
            let shares = try XCTUnwrap(list["result"]["workspaces"].array)
            XCTAssertFalse(shares.contains { $0["display_name"] == .string("C93 Acceptance Unshared") })
            let matching = shares.filter { $0["display_name"] == .string("C93 Acceptance Shared") }
            guard matching.count == 1 else { throw XCTSkip("Share exactly one owned C93 Acceptance Shared fixture first") }
            let workspace = matching[0]
            for scope in ["view", "edit", "build", "test", "run"] {
                guard workspace["permissions"]["studio." + scope] == .string("allow") else { throw XCTSkip("Owned fixture scopes must already be Allow") }
            }
            func request(_ operation: String, _ arguments: ConnectJSON = .object([:])) throws -> ConnectJSON {
                try StudioWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: operation,
                    workspace: workspace["workspace_id"].uuid(), revision: workspace["share_revision"].number(1...Int64.max), arguments: arguments)
            }
            func result(_ operation: String, _ arguments: ConnectJSON = .object([:])) async throws -> ConnectJSON {
                let response = try await exchange(request(operation, arguments))
                XCTAssertEqual(response["error"], .null)
                guard response["error"] == .null else { throw StudioWire.failure(response["error"].string ?? "invalid_request") }
                return response["result"]
            }
            let tree = try await result("tree")
            XCTAssertTrue(tree["entries"].array?.contains { $0["path"] == .string("notes.txt") } == true)
            let original = try await result("read", .object(["path": .string("notes.txt")]))
            guard original["text"] == .string("C93 Acceptance original\n") else {
                throw XCTSkip("Owned notes fixture has changed; preserve it instead of overwriting")
            }
            let savedText = "C93 Acceptance automated phone save\n"
            let saved = try await result("save", .object(["path": .string("notes.txt"), "text": .string(savedText), "expected_hash": original["revision"]]))
            let readback = try await result("read", .object(["path": .string("notes.txt")]))
            XCTAssertEqual(readback["text"], .string(savedText))
            XCTAssertEqual(readback["revision"], saved["revision"])
            let stale = try await exchange(request("save", .object(["path": .string("notes.txt"), "text": .string("C93 Acceptance stale draft\n"), "expected_hash": original["revision"]])))
            XCTAssertEqual(stale["error"], .string("revision_conflict"))
            let afterStale = try await result("read", .object(["path": .string("notes.txt")]))
            XCTAssertEqual(afterStale["text"], .string(savedText))
            // Restore only this exact owned fixture using its verified revision.
            _ = try await result("save", .object(["path": .string("notes.txt"), "text": original["text"], "expected_hash": afterStale["revision"]]))
            print("C93 REAL Studio shared tree/read/save/hash/stale rejection passed; owned notes restored")
            for operation in ["build", "test"] {
                let started = try await result(operation)
                let job = try started["job_id"].uuid()
                var terminal = false
                for _ in 0..<120 {
                    let status = try await result("run_status", .object(["job_id": .string(job)]))
                    if !["starting", "running"].contains(status["state"].string ?? "") {
                        XCTAssertEqual(status["state"], .string("completed"))
                        if operation == "test" { XCTAssertEqual(status["tests"]["passed"], .int(1)) }
                        print("C93 REAL Studio \(operation) job=\(job) state=\(status["state"].string ?? "missing")")
                        terminal = true; break
                    }
                    try await Task.sleep(for: .seconds(1))
                }
                XCTAssertTrue(terminal, "Owned job must reach a real terminal result")
            }
            // Prohibited operations/path syntax are unavailable in the production
            // encoder. This is local authority coverage, not remote rejection proof.
            for forbidden in ["terminal", "pty", "debug", "install", "shell", "owner"] {
                XCTAssertThrowsError(try request(forbidden))
            }
            for path in ["/etc/passwd", "../outside", "C:\\outside"] {
                XCTAssertThrowsError(try request("read", .object(["path": .string(path)])))
            }
            if ProcessInfo.processInfo.environment["OLIVE_C93_STUDIO_DISCONNECT"] == "1" {
                // Requires the prior real UI Run to have created this owned log.
                let before = try await result("read", .object(["path": .string("acceptance-runs.txt")]))
                let originalLog = try before["text"].text()
                let run = try await result("run")
                let job = try run["job_id"].uuid()
                var observedStart = false
                for _ in 0..<10 {
                    _ = try await result("run_status", .object(["job_id": .string(job)]))
                    let log = try await result("read", .object(["path": .string("acceptance-runs.txt")]))
                    if log["text"] == .string(originalLog + "START\n") { observedStart = true; break }
                    try await Task.sleep(for: .seconds(1))
                }
                XCTAssertTrue(observedStart, "Verify the desktop process actually started before cutting its channel")
                await channel.close()
                var reconnected: ConnectTransport?
                for _ in 0..<3 {
                    for candidate in discovery.nearby.prefix(8) {
                        let replacement = ConnectTransport(endpoint: candidate.endpoint)
                        do {
                            try await replacement.connect(identity: identity, peer: peer.identity)
                            // A fixed TLS hello precedes server adoption. Wait for
                            // a real read-only response, as normal session setup
                            // does, before using a replacement after teardown.
                            let probe = try StudioWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: "workspaces")
                            let admitted = try StudioWire.response(await replacement.exchangeFrame(kind: 11, id: probe["request_id"].uuid(), payload: probe.canonical), request: probe)
                            guard admitted["error"] == .null else { throw ConnectFailure.peerOffline }
                            reconnected = replacement; break
                        } catch { await replacement.close() }
                    }
                    if reconnected != nil { break }
                    try await Task.sleep(for: .seconds(1))
                }
                let replacement = try XCTUnwrap(reconnected)
                do {
                    func afterDisconnect(_ operation: String, _ arguments: ConnectJSON) async throws -> ConnectJSON {
                        let req = try request(operation, arguments)
                        return try StudioWire.response(await replacement.exchangeFrame(kind: 11, id: req["request_id"].uuid(), payload: req.canonical), request: req)
                    }
                    let oldStatus = try await afterDisconnect("run_status", .object(["job_id": .string(job)]))
                    XCTAssertEqual(oldStatus["error"], .string("workspace_unavailable"), "C8 jobs do not migrate to a replacement channel")
                    // Observe through the owned program's entire 75-second sleep.
                    // No new Run is submitted. Read-only probes are bounded.
                    for _ in 0..<16 {
                        try await Task.sleep(for: .seconds(5))
                        let read = try await afterDisconnect("read", .object(["path": .string("acceptance-runs.txt")]))
                        XCTAssertEqual(read["error"], .null)
                        XCTAssertEqual(read["result"]["text"], .string(originalLog + "START\n"), "Disconnected job must not finish late or restart")
                    }
                    print("C93 REAL Studio disconnect job=\(job); replacement channel cannot adopt job; 80-second owned log observation shows no DONE and no replay")
                    await replacement.close()
                } catch { await replacement.close(); throw error }
            }
            await channel.close()
        } catch { await channel.close(); throw error }
    }
}

final class RealSyncAcceptanceTests: XCTestCase {
    @MainActor func testOwnedTombstonesAndColdResync() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_DELETE_ACCEPTANCE"] == "1", "Explicit owned-fixture deletion phase only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let vectors = try XCTUnwrap(ProtectedStore<[String: [String: Int64]]>(url: URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/conflict-vectors-v1.json"), maximumBytes: 16384).load())
        XCTAssertEqual(vectors.count, 4)
        let session = ConnectSession(); session.activate()
        defer { session.suspend() }
        for _ in 0..<200 { if session.connected { break }; try await Task.sleep(for: .milliseconds(100)) }
        let (_, _, peer) = try await session.context()
        let model = SyncModel(session: session)
        for domain in ["tasks", "calendar", "reminders", "chat"] { await model.sync(domain) }
        let owned = try vectors.keys.map { try XCTUnwrap(model.store.snapshot.records[$0]) }
        let task = try XCTUnwrap(owned.first { $0.kind == "task" })
        for record in owned where !record.deleted {
            XCTAssertNotEqual(model.recordState(record), "Conflict · review required")
            if record.kind == "reminder" {
                XCTAssertEqual(record.payload["target_id"], .string(task.id))
            } else { XCTAssertTrue(record.payload["title"].string?.hasPrefix("C93 Acceptance ") == true) }
        }
        if !task.deleted { XCTAssertEqual(task.payload["status"], .string("completed")) }
        // Delete dependents first, through the production authoring path. Only
        // the four IDs reviewed in the preceding real conflict phase qualify.
        for kind in ["reminder", "event", "task", "conversation"] {
            let record = try XCTUnwrap(owned.first { $0.kind == kind })
            if !record.deleted {
                if kind == "conversation" { await model.deleteConversation(record) }
                else { _ = try await model.save(kind: kind, payload: .object([:]), old: record, deleted: true) }
            }
            let domain = try XCTUnwrap(SyncWire.domains[kind])
            await model.sync(domain); await model.sync(domain)
            let deleted = try XCTUnwrap(model.store.snapshot.records[record.id])
            XCTAssertTrue(deleted.deleted)
            XCTAssertTrue(model.store.snapshot.acknowledged[peer.id + ":" + domain]?.contains(deleted.revision) == true)
        }
        // Fresh protected-store load, then repeated explicit network sync.
        let cold = SyncModel(session: session, store: MobileSyncStore())
        for _ in 0..<2 { for domain in ["tasks", "calendar", "reminders", "chat"] { await cold.sync(domain) } }
        for id in vectors.keys { XCTAssertTrue(cold.store.snapshot.records[id]?.deleted == true) }
        XCTAssertFalse(cold.records.contains { !$0.deleted && $0.payload["title"] == .string("C93 Acceptance Private") })
        let conversation = try XCTUnwrap(owned.first { $0.kind == "conversation" })
        XCTAssertTrue(cold.records.filter { $0.kind == "message" && cold.store.snapshot.messageParents[$0.id] == conversation.id }.allSatisfy(\.deleted))
        print("C93 REAL Task/Event/Reminder/selected-conversation tombstones acknowledged; all selected messages tombstoned; cold store and repeated sync do not resurrect; unselected Private absent")
    }
    @MainActor func testResolvedConflictsAndOrderedMessageTombstone() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_RESOLVED_ACCEPTANCE"] == "1", "Explicit owner-resolved conflict phase only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let vectors = try XCTUnwrap(ProtectedStore<[String: [String: Int64]]>(url: URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/conflict-vectors-v1.json"), maximumBytes: 16384).load())
        XCTAssertEqual(vectors.count, 4)
        let session = ConnectSession(); session.activate()
        defer { session.suspend() }
        for _ in 0..<200 {
            if session.connected { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        let (_, _, peer) = try await session.context()
        let model = SyncModel(session: session)
        for domain in ["tasks", "calendar", "reminders", "chat"] { await model.sync(domain) }
        var resolved: [SignedSyncRecord] = []
        for (id, vector) in vectors {
            let record = try XCTUnwrap(model.store.snapshot.records[id])
            guard !record.deleted, SyncWire.dominates(record.vector, vector), record.vector != vector,
                  model.recordState(record) != "Conflict · review required" else {
                XCTFail("Owner resolution must dominate the recorded conflict before further mutation"); return
            }
            resolved.append(record)
        }
        for domain in ["tasks", "calendar", "reminders", "chat"] {
            await model.sync(domain)
            XCTAssertFalse(MobileSyncStore.hasConflict(domain: domain, peer: peer.id, in: MobileSyncStore().snapshot))
        }
        let task = try XCTUnwrap(resolved.first { $0.kind == "task" })
        let event = try XCTUnwrap(resolved.first { $0.kind == "event" })
        let conversation = try XCTUnwrap(resolved.first { $0.kind == "conversation" })
        XCTAssertEqual(task.payload["title"], .string("C93 Acceptance Task Desktop Conflict"))
        XCTAssertEqual(event.payload["title"], .string("C93 Acceptance Calendar Desktop Conflict"))
        XCTAssertEqual(conversation.payload["title"], .string("C93 Acceptance Chat Desktop Conflict"))
        let instances = try SyncCalendar.occurrences(event.payload, after: SyncDate.parse("2026-10-01", dateOnly: true), before: SyncDate.parse("2026-10-06", dateOnly: true))
        XCTAssertEqual(instances.compactMap { $0["start"].string }.sorted(), ["2026-10-01", "2026-10-04"])
        var payload = task.payload.object!
        payload["status"] = .string("completed"); payload["completed_at"] = .string(SyncWire.now())
        let completed = try await model.save(kind: "task", payload: .object(payload), old: task)
        await model.sync("tasks")
        XCTAssertTrue(model.store.snapshot.acknowledged[peer.id + ":tasks"]?.contains(completed.revision) == true)
        let first = try XCTUnwrap(model.records.first { !$0.deleted && $0.kind == "message" &&
            model.store.snapshot.messageParents[$0.id] == conversation.id && $0.payload["content"] == .string("Reply with C93 FIRST") })
        let later = try XCTUnwrap(model.records.first { !$0.deleted && $0.kind == "message" &&
            model.store.snapshot.messageParents[$0.id] == conversation.id && $0.payload["content"] == .string("Reply with C93 SECOND") })
        let tombstone = try await model.save(kind: "message", payload: .object([:]), old: first, deleted: true)
        await model.sync("chat"); await model.sync("chat")
        XCTAssertTrue(model.store.snapshot.acknowledged[peer.id + ":chat"]?.contains(tombstone.revision) == true)
        let cold = MobileSyncStore().snapshot
        XCTAssertTrue(cold.records[first.id]?.deleted == true)
        XCTAssertEqual(cold.records[later.id]?.payload["content"], .string("Reply with C93 SECOND"))
        XCTAssertEqual(cold.messageParents[first.id], conversation.id)
        XCTAssertNotNil(cold.messagePredecessors?[first.id])
        print("C93 REAL four conflicts cleared by dominating resolutions; moved/cancelled recurrence correct; linked task completion acknowledged; message tombstone=\(first.id) later message=\(later.id) retained")
    }

    @MainActor func testRealConcurrentConflicts() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_CONFLICT_ACCEPTANCE"] == "1", "Explicit real conflict phase only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let session = ConnectSession(); session.activate()
        defer { session.suspend() }
        for _ in 0..<200 {
            if session.connected { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        let (_, _, peer) = try await session.context()
        let model = SyncModel(session: session)
        let titles = ["C93 Acceptance Task Phone Conflict", "C93 Acceptance Calendar Phone Conflict", "C93 Acceptance Chat Phone Conflict"]
        var owned = model.records.filter { !$0.deleted && titles.contains($0.payload["title"].string ?? "") }
        XCTAssertEqual(owned.count, 3)
        let task = try XCTUnwrap(owned.first { $0.kind == "task" })
        let reminder = try XCTUnwrap(model.records.first { !$0.deleted && $0.kind == "reminder" && $0.payload["target_id"] == .string(task.id) })
        XCTAssertEqual(reminder.payload["at"], .string("2026-10-01T08:30:00+00:00"))
        owned.append(reminder)
        var vectors: [String: [String: Int64]] = [:]
        for domain in ["tasks", "calendar", "reminders", "chat"] {
            await model.sync(domain)
            let record = try XCTUnwrap(owned.first { SyncWire.domains[$0.kind] == domain })
            XCTAssertEqual(model.recordState(record), "Conflict · review required", "\(domain): \(model.notice)")
            XCTAssertEqual(model.store.snapshot.records[record.id]?.revision, record.revision, "No silent destructive merge")
            var vector = record.vector
            for incoming in model.conflicts.filter({ $0.recordID == record.id }).map(\.incoming) {
                for (author, count) in incoming.vector { vector[author] = max(vector[author] ?? 0, count) }
            }
            vectors[record.id] = vector
            await model.sync(domain)
            XCTAssertEqual(model.recordState(record), "Conflict · review required", "Empty/duplicate exchange cannot clear conflict")
            XCTAssertTrue(MobileSyncStore.hasConflict(domain: domain, peer: peer.id, in: MobileSyncStore().snapshot))
            print("C93 REAL \(domain) concurrent conflict retained through repeat sync/store reload; record=\(record.id)")
        }
        try ProtectedStore<[String: [String: Int64]]>(url: URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/conflict-vectors-v1.json"), maximumBytes: 16384).save(vectors)
    }

    @MainActor func testDesktopEditsAndPrepareConflicts() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_EDIT_ACCEPTANCE"] == "1", "Explicit second real-device sync phase only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let session = ConnectSession(); session.activate()
        defer { session.suspend() }
        for _ in 0..<200 {
            if session.connected { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        let (_, _, peer) = try await session.context()
        let model = SyncModel(session: session)
        for domain in ["tasks", "calendar", "reminders", "chat"] {
            await model.sync(domain)
            print("C93 REAL edit-phase sync \(domain): \(model.notice)")
        }
        func named(_ kind: String, _ title: String) throws -> SignedSyncRecord {
            let matches = model.records.filter { !$0.deleted && $0.kind == kind && $0.payload["title"] == .string(title) }
            let syntheticTitles = model.records.filter { !$0.deleted && $0.kind == kind && $0.payload["title"].string?.lowercased().hasPrefix("c93 acceptance") == true }.compactMap { $0.payload["title"].string }
            XCTAssertEqual(matches.count, 1, "Expected \(title); synthetic titles: \(syntheticTitles)")
            return try XCTUnwrap(matches.first, title)
        }
        let task = try named("task", "C93 Acceptance Task Desktop")
        let event = try named("event", "C93 Acceptance Calendar Desktop")
        let chat = try named("conversation", "C93 Acceptance Shared")
        let reminders = model.records.filter { !$0.deleted && $0.kind == "reminder" && $0.payload["target_id"] == .string(task.id) }
        XCTAssertEqual(reminders.count, 1)
        let reminder = try XCTUnwrap(reminders.first)
        XCTAssertNotEqual(reminder.payload["at"], .string("2026-10-01T07:00:00+00:00"))
        var edited: [SignedSyncRecord] = []
        for (record, title) in [(task, "C93 Acceptance Task Phone"), (event, "C93 Acceptance Calendar Phone")] {
            var payload = record.payload.object!; payload["title"] = .string(title)
            edited.append(try await model.save(kind: record.kind, payload: .object(payload), old: record))
        }
        var reminderPayload = reminder.payload.object!
        reminderPayload["at"] = .string("2026-10-01T08:15:00+00:00")
        edited.append(try await model.save(kind: "reminder", payload: .object(reminderPayload), old: reminder))
        for domain in ["tasks", "calendar", "reminders"] { await model.sync(domain) }
        for record in edited {
            let key = peer.id + ":" + SyncWire.domains[record.kind]!
            XCTAssertTrue(model.store.snapshot.acknowledged[key]?.contains(record.revision) == true)
            XCTAssertFalse(MobileSyncStore.hasConflict(domain: SyncWire.domains[record.kind]!, peer: peer.id, in: model.store.snapshot))
        }
        print("C93 REAL desktop edits pulled; phone title/time edits acknowledged for task/event/reminder")
        // Prepare concurrent phone versions without sending them. The next
        // owner batch edits the same common desktop revisions, then explicit
        // sync establishes actual cross-device conflicts.
        for record in edited + [chat] {
            let current = try XCTUnwrap(model.store.snapshot.records[record.id])
            var payload = current.payload.object!
            if current.kind == "reminder" { payload["at"] = .string("2026-10-01T08:30:00+00:00") }
            else { payload["title"] = .string(current.kind == "task" ? "C93 Acceptance Task Phone Conflict" : current.kind == "event" ? "C93 Acceptance Calendar Phone Conflict" : "C93 Acceptance Chat Phone Conflict") }
            let pending = try await model.save(kind: current.kind, payload: .object(payload), old: current)
            if current.kind == "conversation" { model.select(current.id, true) }
            XCTAssertEqual(model.recordState(pending), "Pending sync")
            print("C93 REAL prepared unsent \(current.kind) conflict record=\(current.id) base=\(current.revision) local=\(pending.revision)")
        }
    }

    @MainActor func testOwnedTodayAndSelectedChat() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_SYNC_ACCEPTANCE"] == "1", "Explicit real iPhone/CachyOS acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let session = ConnectSession(); session.activate()
        defer { session.suspend() }
        for _ in 0..<200 {
            if session.connected { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        let (channel, identity, peer) = try await session.context()
        let capabilities = try await channel.exchange(InferenceWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: "capabilities"))
        for domain in ["tasks", "calendar", "reminders", "chat"] {
            guard capabilities["result"]["permissions"]["sync." + domain] == .string("allow") else {
                throw XCTSkip("Desktop sync \(domain) is not Allow; no policy changes are made by this test")
            }
        }
        let model = SyncModel(session: session)
        XCTAssertTrue(model.store.available)
        func sync(_ domain: String, record: SignedSyncRecord? = nil) async throws {
            await model.sync(domain)
            XCTAssertEqual(model.domainStatus[domain], "Sync permitted · last exchange verified")
            if let record {
                XCTAssertTrue(model.store.snapshot.acknowledged[peer.id + ":" + domain]?.contains(record.revision) == true)
                XCTAssertFalse(MobileSyncStore.hasConflict(domain: domain, peer: peer.id, in: model.store.snapshot))
            }
        }
        func owned(_ kind: String, _ payload: ConnectJSON) async throws -> SignedSyncRecord {
            let existing = model.records.filter { $0.kind == kind && !$0.deleted && $0.payload == payload }
            if let first = existing.first { XCTAssertEqual(existing.count, 1); return first }
            // Refuse to overwrite an owner-edited fixture under the same title.
            if let title = payload["title"].string {
                guard !model.records.contains(where: { $0.kind == kind && !$0.deleted && ($0.payload["title"] == .string(title) || $0.payload["title"].string?.hasPrefix("C93 Acceptance") == true) }) else {
                    throw XCTSkip("Synthetic fixture was edited; retain it for the next acceptance phase")
                }
            }
            return try await model.save(kind: kind, payload: payload)
        }
        var taskPayload = SyncPayload.task(title: "C93 Acceptance Task").object!
        taskPayload["due"] = .string("2026-10-01")
        taskPayload["timezone"] = .string("Africa/Johannesburg")
        let task = try await owned("task", .object(taskPayload))
        try await sync("tasks", record: task)
        let calendar = try await owned("calendar", .object(["title": .string("C93 Acceptance Calendar"), "colour": .string("#5b9bff"), "visible": .bool(true)]))
        let event = try await owned("event", .object([
            "calendar_id": .string(calendar.id), "title": .string("C93 Acceptance Calendar Event"), "description": .string(""),
            "location": .string(""), "project_id": .string(""), "timezone": .string("Africa/Johannesburg"), "all_day": .bool(true),
            "status": .string("confirmed"), "transparent": .bool(false), "contact_ids": .array([]), "unsupported": .array([]),
            "original_ics": .string(""), "start": .string("2026-10-01"), "end": .string("2026-10-02"),
            "recurrence": .string("FREQ=DAILY;COUNT=3"), "exceptions": .object([:])]))
        try await sync("calendar", record: event)
        let reminder = try await owned("reminder", .object(["target_kind": .string("task"), "target_id": .string(task.id),
            "at": .string("2026-10-01T07:00:00+00:00"), "offset_minutes": .int(0), "timezone": .string("Africa/Johannesburg")]))
        try await sync("reminders", record: reminder)
        for domain in ["tasks", "calendar", "reminders"] { try await sync(domain) }
        let reloaded = MobileSyncStore()
        for record in [task, calendar, event, reminder] {
            XCTAssertEqual(reloaded.snapshot.records[record.id]?.revision, model.store.snapshot.records[record.id]?.revision)
            print("C93 REAL \(record.kind) stable record=\(record.id) revision=\(record.revision)")
        }
        try await sync("chat")
        let selected = model.records.filter { $0.kind == "conversation" && !$0.deleted && $0.payload["title"] == .string("C93 Acceptance Shared") }
        XCTAssertEqual(selected.count, 1)
        XCTAssertFalse(model.records.contains { $0.kind == "conversation" && !$0.deleted && $0.payload["title"] == .string("C93 Acceptance Private") })
        let conversation = try XCTUnwrap(selected.first)
        let messages = model.records.filter { $0.kind == "message" && !$0.deleted && model.store.snapshot.messageParents[$0.id] == conversation.id }
        XCTAssertEqual(messages.count, 4, "Two synthetic desktop prompts and their answers")
        var after: String? = nil, ordered: [SignedSyncRecord] = []
        for _ in 0..<messages.count {
            let next = messages.filter { $0.payload["after"].string == after }
            XCTAssertEqual(next.count, 1, "Exact linked message ordering")
            guard let record = next.first else { break }
            ordered.append(record); after = record.id
        }
        XCTAssertEqual(ordered.first?.payload["content"], .string("Reply with C93 FIRST"))
        if ordered.count == 4 { XCTAssertEqual(ordered[2].payload["content"], .string("Reply with C93 SECOND")) }
        let revisions = Dictionary(uniqueKeysWithValues: messages.map { ($0.id, $0.revision) })
        try await sync("chat"); try await sync("chat")
        for (id, revision) in revisions { XCTAssertEqual(model.store.snapshot.records[id]?.revision, revision) }
        XCTAssertEqual(model.records.filter { $0.kind == "message" && !$0.deleted && model.store.snapshot.messageParents[$0.id] == conversation.id }.count, 4)
        print("C93 REAL selected Chat conversation=\(conversation.id) ordered messages=\(ordered.map(\.id).joined(separator: ",")); repeat sync stable; named unselected conversation absent")
        let chatStore = MobileChatStore()
        let prompt = "Reply with C93 MOBILE ONLY ONCE"
        let turn: MobileChatTurn
        if let completed = chatStore.turns.first(where: { $0.peerID == peer.id && $0.user == prompt }) {
            turn = completed // A repeated acceptance run never regenerates it.
        } else {
            let startJournal = ProtectedStore<String>(url: URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/c7-start-v1.json"), maximumBytes: 1024)
            guard try startJournal.load() == nil else { throw XCTSkip("An earlier synthetic C7 start has no completed turn; reconcile before an explicit retry") }
            let request = try InferenceWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: "start",
                arguments: InferenceWire.startArguments(preset: "normal", messages: [("user", prompt)]))
            try startJournal.save(request["job_id"].uuid())
            let started = try await channel.exchange(request)
            guard started["error"] == .null else { throw InferenceWire.failure(started["error"].string ?? "invalid_request") }
            let job = try request["job_id"].uuid()
            var answer = InferenceAccumulator()
            for _ in 0..<120 {
                let response = try await channel.exchange(InferenceWire.request(source: identity.publicIdentity.deviceID, target: peer.id,
                    operation: "poll", job: job, arguments: .object(["after": .int(answer.sequence)])))
                guard response["error"] == .null else { throw InferenceWire.failure(response["error"].string ?? "invalid_request") }
                try answer.consume(response["result"])
                if InferenceWire.terminal.contains(answer.state) { break }
                try await Task.sleep(for: .seconds(1))
            }
            guard answer.state == "completed", !answer.text.isEmpty else { throw ConnectFailure.inferenceFailed }
            turn = MobileChatTurn(id: job, userID: UUID().uuidString.lowercased(), assistantID: UUID().uuidString.lowercased(),
                peerID: peer.id, preset: "normal", user: prompt, answer: answer.text, createdAt: Date())
            try chatStore.append(turn)
        }
        await model.selectMobileChat([turn]) // Only this completed synthetic turn.
        try await sync("chat")
        for id in [turn.userID, turn.assistantID] {
            let record = try XCTUnwrap(model.store.snapshot.records[id])
            XCTAssertTrue(model.store.snapshot.acknowledged[peer.id + ":chat"]?.contains(record.revision) == true)
        }
        await model.selectMobileChat([turn]); try await sync("chat"); try await sync("chat")
        XCTAssertEqual(model.records.filter { $0.id == turn.userID || $0.id == turn.assistantID }.count, 2)
        XCTAssertTrue(MobileSyncStore().snapshot.importedTurns.contains(turn.id))
        print("C93 REAL completed C7 turn=\(turn.id) selected once; stable user=\(turn.userID) assistant=\(turn.assistantID); repeated import/sync has two messages")
    }
}

final class ConnectProtocolTests: XCTestCase {
    func testIncomingInferenceProbeKeepsClientAuthorityDenied() throws {
        let local = UUID().uuidString.lowercased(), peer = UUID().uuidString.lowercased()
        for operation in ["status", "capabilities", "start", "poll", "cancel"] {
            let arguments: ConnectJSON = operation == "start" ? try InferenceWire.startArguments(preset: "normal", messages: [("user", "Synthetic probe")]) :
                operation == "poll" ? .object(["after": .int(0)]) : .object([:])
            let request = try InferenceWire.request(source: peer, target: local, operation: operation, arguments: arguments, now: 1000)
            let reply = try InferenceWire.response(InferenceWire.clientReply(request.canonical, local: local, peer: peer, now: 1001).canonical)
            XCTAssertEqual(reply["request_id"], request["request_id"]); XCTAssertEqual(reply["job_id"], request["job_id"])
            if operation == "status" {
                XCTAssertEqual(reply["error"], .null)
                XCTAssertEqual(reply["result"]["permission"], .string("deny"))
                XCTAssertEqual(reply["result"]["busy"], .bool(false))
                XCTAssertTrue(reply["result"]["presets"].object!.values.allSatisfy { $0 == .bool(false) })
            } else { XCTAssertEqual(reply["error"], .string("permission_denied")); XCTAssertEqual(reply["result"], .null) }
            XCTAssertThrowsError(try InferenceWire.clientReply(request.canonical, local: peer, peer: local, now: 1001))
            XCTAssertEqual(try InferenceWire.clientReply(request.canonical, local: local, peer: peer, now: 1120)["error"], .string("expired_request"))
            for (key, value) in [("protocol_version", ConnectJSON.string("olive-inference/2")), ("extra", .bool(true)),
                                 ("expires_at", .int(1121)), ("operation", .string("terminal")), ("arguments", .object(["unexpected": .bool(true)]))] {
                var bad = request.object!; bad[key] = value
                XCTAssertThrowsError(try InferenceWire.clientReply(ConnectJSON.object(bad).canonical, local: local, peer: peer, now: 1001))
            }
        }
    }
    private func vectors() throws -> ConnectJSON {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "vectors", withExtension: "json"))
        return try ConnectJSON.decode(Data(contentsOf: url), limit: 200_000)
    }
    func testCanonicalPythonVectors() throws {
        let v = try vectors()
        let offer = try PairingOffer(v["offer"].canonical, now: v["offer"]["created_at"].integer!)
        let reply = try PairingOffer(v["reply"].canonical, now: v["offer"]["created_at"].integer!)
        XCTAssertEqual(offer.identity.fingerprint, v["fingerprint"].string)
        XCTAssertEqual(ConnectJSON.array([offer.wire,reply.wire]).digest, v["binding"].string)
        XCTAssertEqual(String(decoding: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: reply.identity.deviceID), as: UTF8.self), v["receipt_message"].string)
        for name in ["start","poll","cancel","status","response","capabilities"] {
            let frame = try ConnectFrame(kind: name == "response" || name == "capabilities" ? 10 : 9, payload: v[name].canonical).encode()
            XCTAssertEqual(frame.hex, v[name + "_frame"].string)
            XCTAssertEqual(try ConnectFrame.header(Data(frame.prefix(6))).0, v[name].canonical.count)
        }
        _ = try InferenceWire.response(v["capabilities"].canonical)
        for code in ["busy", "rate_limited", "model_unavailable", "unknown_request"] {
            let value = try InferenceWire.response(v["admission_errors"][code].canonical)
            XCTAssertEqual(value["error"], .string(code)); XCTAssertEqual(value["result"], .null)
            XCTAssertEqual(try ConnectFrame(kind: 10, payload: value.canonical).encode().hex, v["admission_error_frames"][code].string)
        }
        XCTAssertEqual(InferenceWire.failure("rate_limited"), .rateLimited)
        XCTAssertEqual(InferenceWire.failure("busy"), .resourceBusy)
    }
    func testStrictJSONRejectsDuplicatesTruncationAndNonIntegers() {
        for text in ["{\"a\":1,\"a\":2}", "{\"a\":true", "[1,]", "01", "1.0", "NaN", "{\"a\":1,\"\\u0061\":2}"] {
            XCTAssertThrowsError(try ConnectJSON.decode(Data(text.utf8)), text)
        }
    }
    func testFrameLimitsAndVersions() throws {
        XCTAssertThrowsError(try ConnectFrame(kind: 9, payload: Data(repeating: 0, count: 72001)).encode())
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,0,2,4])))
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,1,1,4])))
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,0,1,99])))
        for size in 0..<6 { XCTAssertThrowsError(try ConnectFrame.header(Data(repeating: 0, count: size))) }
    }
    func testPeerIdentityMismatchAndCertificateTampering() throws {
        var identity = try vectors()["offer"]["identity"].object!
        identity["device_id"] = .string(UUID().uuidString.lowercased())
        XCTAssertThrowsError(try ConnectPublicIdentity(.object(identity)))
        identity = try vectors()["offer"]["identity"].object!
        var der = Data(base64Encoded: identity["certificate"]!.string!)!; der[der.count - 1] ^= 1
        identity["certificate"] = .string(der.base64EncodedString())
        XCTAssertThrowsError(try ConnectPublicIdentity(.object(identity)))
    }
    func testInferenceSequenceLimitsAndTerminalSuppression() throws {
        let v = try vectors()
        var accumulator = InferenceAccumulator()
        let r = try InferenceWire.response(v["response"].canonical)["result"]
        try accumulator.consume(r)
        XCTAssertEqual(accumulator.text, "391 🫒")
        XCTAssertThrowsError(try accumulator.consume(r))
        try accumulator.consume(.object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]))
        try accumulator.consume(r)
        XCTAssertEqual(accumulator.text, "391 🫒")
    }
    func testInputBoundsAndPublicRoles() throws {
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "deep", messages: [("user","hi")]))
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "normal", messages: [("user",String(repeating: "🫒", count: 4001))]))
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "normal", messages: [("system","hi")]))
        let v = try vectors()["start"]
        let args = try InferenceWire.startArguments(preset: "normal", messages: [("user", v["arguments"]["messages"].array![0]["content"].text())])
        XCTAssertEqual(args, v["arguments"])
    }
    func testLongConversationKeepsRecentWholeTurnsWithinDesktopBounds() throws {
        let history = (0..<30).flatMap { [("user", "question \($0)"), ("assistant", String(repeating: "🫒", count: 2000))] }
        let context = InferenceWire.context(history: history, user: "next question")
        XCTAssertLessThanOrEqual(context.count, 24)
        XCTAssertLessThanOrEqual(context.reduce(0) { $0 + $1.1.utf8.count }, 48000)
        XCTAssertEqual(context.first?.0, "user")
        XCTAssertEqual(context.last?.1, "next question")
        XCTAssertEqual(context[context.count - 3].1, "question 29")
        _ = try InferenceWire.startArguments(preset: "fast", messages: context)
        let largeAnswer = [("user", "long question"), ("assistant", String(repeating: "x", count: 16001))]
        XCTAssertEqual(InferenceWire.context(history: largeAnswer, user: "next").count, 1)
    }
    func testModelAndSizeFailuresAreNotReportedAsMalformedMessages() {
        XCTAssertEqual(InferenceWire.failure("inference_failed"), .inferenceFailed)
        XCTAssertEqual(InferenceWire.failure("input_too_large"), .inputTooLarge)
        XCTAssertEqual(InferenceWire.failure("output_limit"), .outputLimit)
        XCTAssertEqual(InferenceWire.failure("stream_invalid"), .streamInvalid)
        XCTAssertEqual(InferenceWire.failure("ledger_full"), .requestLedgerFull)
        XCTAssertEqual(InferenceWire.failure("invalid_request"), .responseMalformed)
    }
    @MainActor func testDiscoveryRestartAnnouncesNewCandidateButDoesNotAuthenticate() {
        let discovery = ConnectDiscoveryService()
        var notifications = 0
        discovery.onNewEndpoints = { notifications += 1 }
        let first = NearbyConnectPeer(id: "first", endpoint: .service(name: "first", type: "_olive-connect._tcp", domain: "local.", interface: nil))
        let restart = NearbyConnectPeer(id: "restart", endpoint: .service(name: "restart", type: "_olive-connect._tcp", domain: "local.", interface: nil))
        discovery.updateNearby([first]); discovery.updateNearby([first])
        XCTAssertEqual(notifications, 1)
        discovery.updateNearby([])
        XCTAssertEqual(notifications, 1)
        discovery.updateNearby([restart])
        XCTAssertEqual(notifications, 2)
        XCTAssertEqual(discovery.revision, 2)
        XCTAssertEqual(discovery.nearby.map(\.id), ["restart"])
        discovery.stop()
        XCTAssertTrue(discovery.nearby.isEmpty)
    }
    func testEndpointValidation() {
        for value in ["192.168.1.2", "10.0.0.1", "172.16.0.1", "fd00::1"] { XCTAssertTrue(PairingOffer.localAddress(value)) }
        for value in ["8.8.8.8", "192.168.01.2", "example.local", "fe80::1", "::ffff:192.168.1.2", "0.0.0.0"] { XCTAssertFalse(PairingOffer.localAddress(value)) }
    }
    func testKeychainIdentitySurvivesStoreRecreation() async throws {
        let secrets = KeychainSecretStore(service: "olive.identity.tests.\(UUID().uuidString)")
        do {
            let first = try await ConnectIdentityStore(secrets: secrets).load()
            let second = try await ConnectIdentityStore(secrets: secrets).load()
            XCTAssertEqual(first.publicIdentity, second.publicIdentity)
            let verifier = try Curve25519.Signing.PublicKey(rawRepresentation: first.publicIdentity.publicKey)
            XCTAssertTrue(try verifier.isValidSignature(first.sign(Data("test".utf8)), for: Data("test".utf8)))
            XCTAssertTrue(try verifier.isValidSignature(second.sign(Data("test".utf8)), for: Data("test".utf8)))
            try await secrets.remove(account: "mobile-identity-v1")
            do { _ = try await ConnectIdentityStore(secrets: secrets).load(); XCTFail("Missing private identity must not be replaced") } catch {}
            let absent = try await secrets.read(account: "mobile-identity-v1")
            XCTAssertNil(absent)
            try await secrets.write(Data("corrupt".utf8), account: "mobile-identity-v1")
            do { _ = try await ConnectIdentityStore(secrets: secrets).load(); XCTFail("Must not replace identity") } catch {}
            let preserved = try await secrets.read(account: "mobile-identity-v1")
            XCTAssertEqual(preserved, Data("corrupt".utf8))
            try await secrets.remove(account: "mobile-identity-v1")
            try await secrets.remove(account: "mobile-identity-reservation-v1")
        } catch { try? await secrets.remove(account: "mobile-identity-v1"); try? await secrets.remove(account: "mobile-identity-reservation-v1"); throw error }
    }
    @MainActor func testUnpairAndPendingDoNotCreateTrust() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let repository = ConnectTrustRepository(directory: dir)
        let v = try vectors()
        let offer = try PairingOffer(v["offer"].canonical, now: v["offer"]["created_at"].integer!)
        try repository.reserve(offer)
        XCTAssertTrue(ConnectTrustRepository(directory: dir).peers.isEmpty)
        XCTAssertThrowsError(try repository.reserve(offer))
        try repository.cancel(offer.sessionID)
        XCTAssertThrowsError(try repository.commit(offer: offer, peerReceipt: Data()))
    }
    func testExplicitIdentityResetPersistsNewKey() async throws {
        let secrets = KeychainSecretStore(service: "olive.identity.reset.tests.\(UUID().uuidString)")
        do {
            let store = ConnectIdentityStore(secrets: secrets)
            let old = try await store.load()
            let replacement = try await store.reset()
            XCTAssertNotEqual(old.publicIdentity.deviceID, replacement.publicIdentity.deviceID)
            XCTAssertNotEqual(old.publicIdentity.publicKey, replacement.publicIdentity.publicKey)
            let restored = try await ConnectIdentityStore(secrets: secrets).load(allowCreation: false)
            XCTAssertEqual(restored.publicIdentity, replacement.publicIdentity)
            let verifier = try Curve25519.Signing.PublicKey(rawRepresentation: restored.publicIdentity.publicKey)
            let message = Data("reset acceptance".utf8)
            XCTAssertTrue(try verifier.isValidSignature(restored.sign(message), for: message))
            XCTAssertFalse(try verifier.isValidSignature(old.sign(message), for: message))
            try await secrets.remove(account: "mobile-identity-v1")
            try await secrets.remove(account: "mobile-identity-reservation-v1")
        } catch {
            try? await secrets.remove(account: "mobile-identity-v1")
            try? await secrets.remove(account: "mobile-identity-reservation-v1")
            throw error
        }
    }
    func testInterruptedIdentityResetRequiresExplicitRecovery() async throws {
        let secrets = ResetFaultSecretStore()
        let store = ConnectIdentityStore(secrets: secrets)
        let original = try await store.load()
        let originalEnvelope = try await secrets.read(account: "mobile-identity-v1")
        await secrets.failNextEnvelopeWrite()
        do { _ = try await store.reset(); XCTFail("Expected injected Keychain failure") } catch {}
        let retainedEnvelope = try await secrets.read(account: "mobile-identity-v1")
        XCTAssertEqual(retainedEnvelope, originalEnvelope)
        for loader in [store, ConnectIdentityStore(secrets: secrets)] {
            do { _ = try await loader.load(); XCTFail("Interrupted reset must fail closed") } catch {}
        }
        let replacement = try await store.reset()
        let restored = try await ConnectIdentityStore(secrets: secrets).load(allowCreation: false)
        XCTAssertEqual(restored.publicIdentity, replacement.publicIdentity)
        XCTAssertNotEqual(restored.publicIdentity.publicKey, original.publicIdentity.publicKey)
    }
    @MainActor func testReceiptRecoveryRequiresOriginalLocalConfirmationAndUnpairRemovesPin() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let local = try ConnectIdentity.generate(), remote = try ConnectIdentity.generate()
        let now = Int64(Date().timeIntervalSince1970)
        let offer = try PairingOffer(ConnectJSON.object(["protocol": .string("olive-pairing-tls13/2"), "session_id": .string(UUID().uuidString.lowercased()),
            "created_at": .int(now), "expires_at": .int(now+120), "identity": remote.publicIdentity.wire,
            "endpoint": .object(["address": .string("192.168.1.2"), "port": .int(54321)]), "display_name": .string("Fixture")]).canonical)
        let reply = try offer.reply(identity: local.publicIdentity, name: "Phone")
        let localReceipt = try local.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: local.publicIdentity.deviceID))
        let peerReceipt = try remote.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: remote.publicIdentity.deviceID))
        let completion = ConnectJSON.object(["protocol": .string("olive-pairing-completion/1"), "offer": offer.wire, "reply": reply.wire,
            "receipts": .object([local.publicIdentity.deviceID: .string(localReceipt.base64EncodedString()), remote.publicIdentity.deviceID: .string(peerReceipt.base64EncodedString())])])
        let repository = ConnectTrustRepository(directory: dir)
        try repository.reserve(offer)
        XCTAssertThrowsError(try repository.importCompletion(completion.canonical))
        try repository.recordConfirmation(offer: offer, reply: reply, receipt: localReceipt)
        XCTAssertThrowsError(try repository.commit(offer: offer, peerReceipt: Data(repeating: 0, count: 64)))
        let restarted = ConnectTrustRepository(directory: dir)
        XCTAssertTrue(restarted.peers.isEmpty)
        try restarted.importCompletion(completion.canonical)
        XCTAssertEqual(restarted.peers.first?.identity, remote.publicIdentity)
        XCTAssertThrowsError(try restarted.prepareIdentityReset())
        XCTAssertFalse(ConnectSession(repository: restarted).canResetIdentity)
        try restarted.unpair(remote.publicIdentity.deviceID)
        XCTAssertTrue(ConnectTrustRepository(directory: dir).peers.isEmpty)
        let raw = try String(contentsOf: dir.appendingPathComponent("trust-v1.json"), encoding: .utf8)
        XCTAssertFalse(raw.contains(remote.publicIdentity.certificate.base64EncodedString()))
        XCTAssertThrowsError(try restarted.importCompletion(completion.canonical))
        let interrupted = ConnectTrustRepository(directory: dir.appendingPathComponent("interrupted"))
        try interrupted.reserve(offer)
        try interrupted.recordConfirmation(offer: offer, reply: reply, receipt: localReceipt)
        XCTAssertEqual(interrupted.interruptedSessions, [offer.sessionID])
        try interrupted.prepareIdentityReset()
        let afterReset = ConnectTrustRepository(directory: dir.appendingPathComponent("interrupted"))
        XCTAssertTrue(afterReset.interruptedSessions.isEmpty)
        XCTAssertThrowsError(try afterReset.importCompletion(completion.canonical))
        XCTAssertThrowsError(try afterReset.reserve(offer))
    }
    @MainActor func testNearbyBoundedDeduplicationAndRemovalSnapshot() {
        let entries = (0..<80).map { NearbyConnectPeer(id: String($0), endpoint: .service(name: String($0), type: "_olive-connect._tcp", domain: "local.", interface: nil)) }
        XCTAssertEqual(ConnectDiscoveryService.bounded(entries).count, 64)
        XCTAssertEqual(ConnectDiscoveryService.bounded([entries[0],entries[0]]).count, 1)
        XCTAssertTrue(ConnectDiscoveryService.bounded([]).isEmpty)
    }
    func testCodeRenderingPreservesFencedContent() {
        XCTAssertEqual(ChatMessage.parse("Example\n```swift\nfunc even(_ n: Int) -> Bool { n % 2 == 0 }\n```"),
            [.text("Example"), .code(language: "swift", content: "func even(_ n: Int) -> Bool { n % 2 == 0 }")])
    }
}

private actor ResetFaultSecretStore: SecretStore {
    private var values: [String: Data] = [:]
    private var failEnvelope = false
    func failNextEnvelopeWrite() { failEnvelope = true }
    func read(account: String) throws -> Data? { values[account] }
    func write(_ data: Data, account: String) throws {
        if account == "mobile-identity-v1", failEnvelope {
            failEnvelope = false
            throw ConnectFailure.identityRecoveryRequired
        }
        values[account] = data
    }
    func remove(account: String) throws { values.removeValue(forKey: account) }
}

private actor InferenceTestTransport: InferenceTransport {
    var generating = false
    var released = false
    var calls: [String] = []
    var polls = 0
    var hold = false
    let rejectStart: Bool
    let failPoll: Bool
    let terminalError: String?
    init(hold: Bool = false, rejectStart: Bool = false, failPoll: Bool = false, terminalError: String? = nil) {
        self.hold = hold; self.rejectStart = rejectStart; self.failPoll = failPoll
        self.terminalError = terminalError
    }
    func exchange(_ req: ConnectJSON) async throws -> ConnectJSON {
        let operation = req["operation"].string!
        calls.append(operation)
        var result: ConnectJSON
        switch operation {
        case "start":
            if rejectStart { throw ConnectFailure.permissionDenied }
            generating = true; released = false; polls = 0
            result = .object(["state": .string("queued"), "events": .array([]), "error": .null])
        case "cancel":
            // Represents the release acknowledgement, not a renderer-only stop.
            try await Task.sleep(for: .milliseconds(100))
            generating = false; released = true; hold = false
            result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")])
        default:
            if failPoll { throw ConnectFailure.connectionLost }
            if hold { try await Task.sleep(for: .milliseconds(150)) }
            polls += 1
            if !generating { result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]) }
            else {
                let complete = !hold && polls >= 2
                if complete { generating = false; released = true }
                result = .object(["state": .string(complete ? terminalError == nil ? "completed" : "failed" : "streaming"),
                    "events": .array([.object(["sequence": .int(Int64(polls)), "text": .string(polls == 1 ? "3" : "91")])]),
                    "error": complete ? terminalError.map(ConnectJSON.string) ?? .null : .null])
            }
        }
        return .object(["protocol_version": .string("olive-inference/1"), "request_id": req["request_id"], "job_id": req["job_id"], "result": result, "error": .null])
    }
    func close() { generating = false }
}
private actor InferenceUpdates {
    var values: [(String,String)] = []
    func append(_ state: String, _ text: String) { values.append((state,text)) }
    var lastText: String? { values.last?.1 }
}
/// Desktop C7 rejects a start with result=null/error=code, without a job.
/// Cancelling that rejected ID returns unknown_request on the same healthy channel.
private actor AdmissionTestTransport: InferenceTransport {
    var rejection: String?
    let failUncertainStart: Bool
    let rejectPoll: Bool
    var calls: [String] = []
    var closes = 0
    private var job: String?
    init(rejection: String? = nil, failUncertainStart: Bool = false, rejectPoll: Bool = false) {
        self.rejection = rejection; self.failUncertainStart = failUncertainStart; self.rejectPoll = rejectPoll
    }
    func allow() { rejection = nil }
    func exchange(_ req: ConnectJSON) async throws -> ConnectJSON {
        guard closes == 0 else { throw ConnectFailure.peerOffline }
        let operation = try req["operation"].text()
        calls.append(operation)
        var error: ConnectJSON = .null, result: ConnectJSON = .null
        switch operation {
        case "start":
            if let rejection { error = .string(rejection) }
            else {
                job = req["job_id"].string
                if failUncertainStart { throw ConnectFailure.connectionLost }
                result = .object(["state": .string("queued"), "events": .array([]), "error": .null])
            }
        case "poll":
            if rejectPoll { error = .string("rate_limited") }
            else { result = .object(["state": .string("completed"), "events": .array([
                .object(["sequence": .int(1), "text": .string("391")])]), "error": .null]); job = nil }
        case "cancel":
            if failUncertainStart { throw ConnectFailure.connectionLost }
            if job == nil { error = .string("unknown_request") }
            else { job = nil; result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]) }
        case "status":
            result = .object(["presets": .object(["fast": .bool(true), "normal": .bool(true), "max": .bool(false)]),
                "permission": .string("allow"), "busy": .bool(false)])
        default: throw ConnectFailure.responseMalformed
        }
        return try InferenceWire.response(ConnectJSON.object(["protocol_version": .string("olive-inference/1"),
            "request_id": req["request_id"], "job_id": req["job_id"], "result": result, "error": error]).canonical)
    }
    func close() { closes += 1; job = nil }
}
final class RemoteLifecycleTests: XCTestCase {
    func testAdmissionRejectionsPreserveChannelAndAllowExplicitRetry() async throws {
        for (code, expected) in [("rate_limited", ConnectFailure.rateLimited), ("busy", .resourceBusy), ("model_unavailable", .capabilityUnavailable)] {
            let transport = AdmissionTestTransport(rejection: code)
            let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
            do {
                try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in XCTFail("Rejected start cannot produce a response") }
                XCTFail("Expected rejection")
            } catch { XCTAssertEqual(error as? ConnectFailure, expected) }
            let rejectedCalls = await transport.calls, closes = await transport.closes
            XCTAssertEqual(rejectedCalls, ["start"]); XCTAssertEqual(closes, 0)
            let status = try await client.status()
            XCTAssertEqual(status["permission"], .string("allow"))
            await transport.allow() // Capacity/cooldown recovers; no reconnect.
            let updates = InferenceUpdates()
            try await client.run(preset: "normal", messages: [("user", "Retry")]) { _, state, text in await updates.append(state, text) }
            let answer = await updates.lastText, finalCloses = await transport.closes
            XCTAssertEqual(answer, "391"); XCTAssertEqual(finalCloses, 0)
        }
    }
    func testUncertainStartStillCancelsAndClosesWhenCleanupFails() async throws {
        let transport = AdmissionTestTransport(failUncertainStart: true)
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        do { try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in }; XCTFail("Expected connection loss") }
        catch { XCTAssertEqual(error as? ConnectFailure, .connectionLost) }
        let calls = await transport.calls, closes = await transport.closes
        XCTAssertEqual(calls, ["start", "cancel"]); XCTAssertEqual(closes, 1)
    }
    func testRejectionAfterAdmissionStillCancelsActualJob() async throws {
        let transport = AdmissionTestTransport(rejectPoll: true)
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        do { try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in }; XCTFail("Expected poll rejection") }
        catch { XCTAssertEqual(error as? ConnectFailure, .rateLimited) }
        let calls = await transport.calls
        XCTAssertEqual(calls, ["start", "poll", "cancel"])
    }
    func testIncrementalRequestAndCompletion() async throws {
        let transport = InferenceTestTransport(), updates = InferenceUpdates()
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        try await client.run(preset: "normal", messages: [("user","17 * 23")]) { _, state, text in await updates.append(state,text) }
        let last = await updates.lastText, calls = await transport.calls
        XCTAssertEqual(last, "391"); XCTAssertEqual(calls, ["start","poll","poll"])
    }
    func testStopWaitsForReleaseSuppressesLatePollAndAllowsNextRequest() async throws {
        let transport = InferenceTestTransport(hold: true), updates = InferenceUpdates()
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        let running = Task { try await client.run(preset: "fast", messages: [("user","example")]) { _, state, text in await updates.append(state,text) } }
        for _ in 0..<100 { if await transport.generating { break }; try await Task.sleep(for: .milliseconds(5)) }
        let state = try await client.stop(), released = await transport.released
        XCTAssertEqual(state, "cancelled"); XCTAssertTrue(released)
        do { try await running.value; XCTFail("Cancelled request cannot complete") } catch {}
        let stoppedText = await updates.lastText
        XCTAssertEqual(stoppedText, "")
        _ = try await client.stop() // Repeated stop is inert.
        try await client.run(preset: "normal", messages: [("user","new request")]) { _, state, text in await updates.append(state,text) }
        let nextText = await updates.lastText
        XCTAssertEqual(nextText, "391")
    }
}

@MainActor private final class ChatTestStore: ShellStore {
    var text = ""
    func loadDestination() -> Destination { .chat }
    func saveDestination(_ value: Destination) {}
    func loadDraft() throws -> String { text }
    func saveDraft(_ value: String) throws { text = value }
}
@MainActor private final class ChatTestConnection: ChatRemoteSession {
    var connected = true
    let selectedID: String? = UUID().uuidString.lowercased()
    var capability: ConnectJSON? = .object(["permission": .string("allow"), "presets": .object(["normal": .bool(true)])])
    let inference: RemoteInferenceClient?
    init(_ transport: any InferenceTransport) {
        inference = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: selectedID!)
    }
}
@MainActor final class MobileChatStateTests: XCTestCase {
    func testRateLimitPreservesDraftAndConnectionWithoutAutomaticRetry() async throws {
        let transport = AdmissionTestTransport(rejection: "rate_limited")
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "Keep this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertTrue(state.canSend)
        XCTAssertEqual(state.draft, "Keep this question")
        XCTAssertTrue(state.chatStatus.contains("request limit")); XCTAssertFalse(state.chatStatus.contains("busy"))
        let calls = await transport.calls, closes = await transport.closes
        XCTAssertEqual(calls, ["start"]); XCTAssertEqual(closes, 0)
        await transport.allow()
        XCTAssertEqual(state.messages.filter { $0.role == .user }.count, 1)
        state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Completed"); XCTAssertTrue(state.draft.isEmpty)
    }
    func testOffAndOfflinePreserveDraftWithoutSending() async throws {
        let transport = InferenceTestTransport(), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Keep this question"
        connection.connected = false
        state.send()
        XCTAssertEqual(state.draft, "Keep this question"); XCTAssertTrue(state.messages.isEmpty)
        connection.connected = true
        connection.capability = .object(["permission": .string("deny"), "presets": .object(["normal": .bool(true)])])
        state.send()
        let calls = await transport.calls
        XCTAssertTrue(calls.isEmpty); XCTAssertFalse(state.canSend)
    }
    func testDuplicateSubmitAndDraftAdmissionThenCompletion() async throws {
        let transport = InferenceTestTransport(), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Question"
        state.send(); state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Completed"); XCTAssertEqual(state.draft, "")
        XCTAssertEqual(state.messages.filter { $0.role == .user }.count, 1)
        let calls = await transport.calls
        XCTAssertEqual(calls.filter { $0 == "start" }.count, 1)
        XCTAssertNotNil(state.messages.last?.attribution?.requestID)
    }
    func testAdmittedStopKeepsComposerAndSavedDraftEmpty() async throws {
        let transport = InferenceTestTransport(hold: true), store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(transport))
        state.draft = "Long request"; state.send()
        for _ in 0..<100 { if state.draft.isEmpty { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(state.draft.isEmpty); XCTAssertTrue(store.text.isEmpty)
        XCTAssertEqual(state.messages.first?.plainText, "Long request")
        state.stop()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Cancelled")
        XCTAssertTrue(state.draft.isEmpty)
        XCTAssertTrue(AppState(store: store).draft.isEmpty)
    }
    func testNewIdenticalDraftSurvivesResponseUpdatesAndStop() async throws {
        let transport = InferenceTestTransport(hold: true)
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "Question"; state.send()
        for _ in 0..<100 { if state.draft.isEmpty { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(state.draft.isEmpty)
        state.draft = "Question" // A new draft may intentionally repeat the sent text.
        for _ in 0..<100 { if await transport.polls >= 2 { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.draft, "Question")
        state.stop()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.draft, "Question")
    }
    func testRejectedStartKeepsDraftAndVisibleFailedTurn() async throws {
        let store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(InferenceTestTransport(rejectStart: true)))
        state.draft = "Keep this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertEqual(state.draft, "Keep this question")
        XCTAssertEqual(store.text, "Keep this question")
        XCTAssertEqual(state.messages.first?.plainText, "Keep this question")
        XCTAssertTrue(state.messages.first?.status?.hasPrefix("Failed") == true)
    }
    func testConnectionFailureRestoresUntouchedAdmittedDraftForExplicitRetry() async throws {
        let store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(InferenceTestTransport(failPoll: true)))
        state.draft = "Retry this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertTrue(state.chatStatus.hasPrefix("Failed"))
        XCTAssertEqual(state.draft, "Retry this question"); XCTAssertEqual(store.text, state.draft)
    }
    func testOutputLimitKeepsPartialAnswerAndRestoresDraftWithoutResending() async throws {
        let transport = InferenceTestTransport(terminalError: "output_limit")
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "A bounded synthetic request"; state.send()
        for _ in 0..<150 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active)
        XCTAssertTrue(state.chatStatus.contains(ConnectFailure.outputLimit.localizedDescription))
        XCTAssertTrue(state.chatStatus.contains("Draft restored; nothing was resent."))
        XCTAssertEqual(state.draft, "A bounded synthetic request")
        XCTAssertEqual(state.messages.last?.plainText, "391")
        XCTAssertEqual(state.messages.last?.status, "Incomplete")
        let calls = await transport.calls
        XCTAssertEqual(calls.filter { $0 == "start" }.count, 1)
        XCTAssertEqual(calls.last, "cancel")
    }
    func testStopBackgroundRaceCannotOverwriteNewState() async throws {
        let transport = InferenceTestTransport(hold: true), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Long request"; state.send()
        for _ in 0..<100 { if await transport.generating { break }; try await Task.sleep(for: .milliseconds(5)) }
        state.stop(); state.suspend()
        let interrupted = state.chatStatus
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertEqual(state.chatStatus, interrupted)
        XCTAssertFalse(state.active)
        XCTAssertTrue(state.messages.allSatisfy { $0.status == "Interrupted · connection closed" })
    }
}

/// Explicit real-device negative test. It never edits production trust or keys,
/// and probes a wrong pin only after authenticating the real paired endpoint.
final class RealConnectSecurityTests: XCTestCase {
    @MainActor func testRealLANWrongPeerPinRejected() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C92_SECURITY_ACCEPTANCE"] == "1",
                          "Requires explicit physical-iPhone / paired desktop acceptance")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let repository = ConnectTrustRepository()
        let before = repository.peers
        let peer = try XCTUnwrap(before.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let discovery = ConnectDiscoveryService()
        discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var authenticated: NWEndpoint?
        for candidate in discovery.nearby.prefix(8) {
            let transport = ConnectTransport(endpoint: candidate.endpoint)
            do {
                try await transport.connect(identity: identity, peer: peer.identity)
                authenticated = candidate.endpoint
            } catch { /* Discovery is untrusted; only a pinned success selects the target. */ }
            await transport.close()
            if authenticated != nil { break }
        }
        let endpoint = try XCTUnwrap(authenticated, "Real paired desktop must pass pinned TLS first")
        let wrongPeer = try ConnectIdentity.generate().publicIdentity
        let rejected = ConnectTransport(endpoint: endpoint)
        do {
            try await rejected.connect(identity: identity, peer: wrongPeer)
            XCTFail("Wrong peer certificate was accepted")
        } catch {
            XCTAssertEqual(error as? ConnectFailure, .certificateMismatch,
                           "A TCP timeout is not evidence of wrong-pin rejection")
        }
        await rejected.close()
        XCTAssertEqual(ConnectTrustRepository().peers, before)
        let after = try await ConnectIdentityStore().load(allowCreation: false)
        XCTAssertEqual(after.publicIdentity, identity.publicIdentity)
        print("C9.2 real LAN: correct pin authenticated; wrong pin rejected; saved identity and trust unchanged")
    }
}

final class RealConnectCancellationTests: XCTestCase {
    @MainActor func testRealLANCancellationBoundaries() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C92_CANCEL_ACCEPTANCE"] == "1", "Explicit physical-device real-model acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let peer = try XCTUnwrap(ConnectTrustRepository().peers.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let source = identity.publicIdentity.deviceID
        let discovery = ConnectDiscoveryService(); discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var selected: (NWEndpoint, ConnectTransport)?
        for candidate in discovery.nearby.prefix(8) {
            let channel = ConnectTransport(endpoint: candidate.endpoint)
            do { try await channel.connect(identity: identity, peer: peer.identity); selected = (candidate.endpoint, channel); break }
            catch { await channel.close() }
        }
        let (endpoint, channel) = try XCTUnwrap(selected, "Authenticate the real paired desktop first")
        func request(_ operation: String, job: String? = nil, arguments: ConnectJSON = .object([:])) throws -> ConnectJSON {
            try InferenceWire.request(source: source, target: peer.id, operation: operation, job: job, arguments: arguments)
        }
        func start(_ channel: ConnectTransport, _ text: String) async throws -> String {
            let req = try request("start", arguments: InferenceWire.startArguments(preset: "normal", messages: [("user", text)]))
            let answer = try await channel.exchange(req)
            XCTAssertEqual(answer["error"], .null)
            guard answer["error"] == .null else { throw ConnectFailure.resourceBusy }
            return try req["job_id"].uuid()
        }
        func cancel(_ channel: ConnectTransport, _ job: String) async throws -> String {
            let answer = try await channel.exchange(request("cancel", job: job))
            XCTAssertEqual(answer["error"], .null)
            return try answer["result"]["state"].text()
        }
        func complete(_ channel: ConnectTransport, _ job: String) async throws {
            var accumulator = InferenceAccumulator()
            let deadline = ContinuousClock.now.advanced(by: .seconds(135))
            while ContinuousClock.now < deadline {
                let answer = try await channel.exchange(request("poll", job: job, arguments: .object(["after": .int(accumulator.sequence)])))
                XCTAssertEqual(answer["error"], .null)
                try accumulator.consume(answer["result"])
                if InferenceWire.terminal.contains(accumulator.state) {
                    XCTAssertEqual(accumulator.state, "completed")
                    XCTAssertFalse(accumulator.text.isEmpty)
                    return
                }
                try await Task.sleep(for: .milliseconds(250))
            }
            throw ConnectFailure.requestTimeout
        }
        do {
            let status = try await channel.exchange(request("status"))
            XCTAssertEqual(status["result"]["permission"], .string("allow"))
            guard status["result"]["permission"] == .string("allow") else { throw ConnectFailure.permissionDenied }
            let longPrompt = "Write a detailed 1000-word explanation of Swift arrays, dictionaries, sets, loops and functions, with small code examples."
            let early = try await start(channel, longPrompt)
            let beforeStop = ContinuousClock.now
            let stopped = try await cancel(channel, early)
            XCTAssertEqual(stopped, "cancelled")
            let repeated = try await cancel(channel, early)
            XCTAssertEqual(repeated, "cancelled")
            print("C9.2 early cancel: \(early) terminal=\(stopped) acknowledgement=\(beforeStop.duration(to: .now)) repeated=\(repeated)")
            let completed = try await start(channel, "What is 17 * 23? Answer with the number and a short explanation.")
            try await complete(channel, completed)
            let raced = try await cancel(channel, completed)
            XCTAssertEqual(raced, "completed", "Late Stop must not relabel a completed task")
            print("C9.2 completion-race cancel: \(completed) terminal=\(raced)")
            let lost = try await start(channel, longPrompt)
            try await channel.acceptanceDisconnectDuringCancel(request("cancel", job: lost))
            let replacement = ConnectTransport(endpoint: endpoint)
            do {
                try await replacement.connect(identity: identity, peer: peer.identity)
                var idle = false
                for _ in 0..<40 {
                    let state = try await replacement.exchange(request("status"))
                    if state["result"]["busy"] == .bool(false) { idle = true; break }
                    try await Task.sleep(for: .milliseconds(250))
                }
                XCTAssertTrue(idle, "Desktop must release inference after the cancel connection is lost")
                let fresh = try await start(replacement, "Explain in two sentences what a hash function does.")
                try await complete(replacement, fresh)
                print("C9.2 cancel acknowledgement deliberately lost: \(lost); fresh pinned connection, desktop idle, new request completed: \(fresh)")
                await replacement.close()
            } catch { await replacement.close(); throw error }
            await channel.close()
        } catch { await channel.close(); throw error }
    }
}

@MainActor
final class BackgroundOperationTests: XCTestCase {
    func testFileBackgroundExpirationPreservesCauseWithoutClaimingUserCancellation() async throws {
        for expired in [true, false] {
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: directory) }
            let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
            let identity = try ConnectIdentity.generate()
            let trust = directory.appendingPathComponent("Trust")
            try FileManager.default.createDirectory(at: trust, withIntermediateDirectories: true)
            let peer = TrustedConnectPeer(identity: identity.publicIdentity, displayName: "Synthetic")
            try ConnectJSON.object(["version": .int(1), "peers": .array([peer.wire]), "ledger": .object([:])]).canonical
                .write(to: trust.appendingPathComponent("trust-v1.json"))
            // Isolated public fixture; never activate or connect this session.
            let session = ConnectSession(repository: ConnectTrustRepository(directory: trust))
            let files = FilesModel(session: session, background: coordinator, directory: directory.appendingPathComponent("Files"))
            let selected = directory.appendingPathComponent("synthetic.bin")
            try Data("test".utf8).write(to: selected)
            await files.select(selected)
            let id = try XCTUnwrap(files.receipts.first?.id)
            XCTAssertEqual(files.receipts.first?.state, "offered")
            try coordinator.begin(BackgroundOperationRecord(id: id, capability: "files.receive", peerID: peer.id,
                label: "Sending file", protocolID: id, requestDigest: "digest", startedAt: Date(), totalUnits: 4)) {
                    await files.cancel(id)
                }
            await coordinator.cancel(expired: expired, source: expired ? .systemExpirationOrStop : .userCancelled)
            coordinator.finish(.completed, id: id)
            let saved = BackgroundWorkCoordinator(directory: directory, register: false).records.last
            XCTAssertEqual(saved?.state, expired ? .expired : .cancelled)
            XCTAssertEqual(saved?.continuationEnd, expired ? .systemExpirationOrStop : .userCancelled)
            XCTAssertEqual(saved?.failure, expired ? .backgroundTaskExpired : .backgroundTaskCancelled)
            XCTAssertNil(saved?.systemReportedSuccess)
            XCTAssertEqual(files.receipts.first?.state, expired ? "interrupted" : "cancelled")
            XCTAssertTrue(files.notice.hasPrefix(expired ? "Background execution ended" : "Cancelled locally"))
            XCTAssertFalse(FileManager.default.fileExists(atPath: try files.staging.path(id, "out").path))
            XCTAssertEqual(try Data(contentsOf: selected), Data("test".utf8))
        }
    }
    func testLaunchNeverReplaysUnfinishedWork() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        let record = BackgroundOperationRecord(id: UUID().uuidString.lowercased(), capability: "files.receive",
            peerID: UUID().uuidString.lowercased(), label: "Sending file", protocolID: UUID().uuidString.lowercased(),
            requestDigest: String(repeating: "a", count: 64), startedAt: Date(), totalUnits: 100)
        try coordinator.begin(record) { XCTFail("Relaunch must not execute a stored callback") }
        try coordinator.progress(40, total: 100)
        XCTAssertThrowsError(try coordinator.progress(39, total: 100))
        XCTAssertThrowsError(try coordinator.progress(101, total: 100))
        XCTAssertFalse(coordinator.continuationGranted)
        let restarted = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertNil(restarted.active)
        XCTAssertEqual(restarted.records.first?.state, .interrupted)
        XCTAssertEqual(restarted.records.first?.verifiedUnits, 40)
        XCTAssertEqual(restarted.records.first?.retrySafety, "explicitFreshRequestOnly")
        XCTAssertEqual(restarted.records.first?.desktopMayContinueIndependently, false)
    }
    func testCancellationIsPersistedBeforeCleanupAndOnlyOnce() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        var calls = 0
        try coordinator.begin(BackgroundOperationRecord(id: "operation", capability: "models.remote", peerID: "peer",
            label: "Receiving response", protocolID: "request", requestDigest: "digest", startedAt: Date())) {
                calls += 1
                XCTAssertNil(coordinator.active)
            }
        await coordinator.cancel(expired: true)
        await coordinator.cancel()
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(coordinator.records.last?.state, .expired)
    }
    func testOldProgressCannotUpdateNewOperationAndV1MetadataMigrates() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        let record = BackgroundOperationRecord(id: "new", capability: "files.receive", peerID: "peer",
            label: "Sending file", protocolID: "new", requestDigest: "digest", startedAt: Date(), totalUnits: 100)
        var legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(record)) as! [String: Any]
        legacy.removeValue(forKey: "scope")
        legacy.removeValue(forKey: "failure")
        legacy.removeValue(forKey: "finishedAt")
        for key in ["continuationGrantedAt", "continuationEnd", "systemCompletedUnits", "systemTotalUnits", "systemReportedSuccess"] { legacy.removeValue(forKey: key) }
        let migrated = try JSONDecoder().decode(BackgroundOperationRecord.self, from: JSONSerialization.data(withJSONObject: legacy))
        XCTAssertNil(migrated.scope)
        XCTAssertNil(migrated.failure)
        XCTAssertNil(migrated.finishedAt)
        XCTAssertNil(migrated.continuationGrantedAt)
        XCTAssertNil(migrated.continuationEnd)
        XCTAssertNil(migrated.systemCompletedUnits)
        XCTAssertNil(migrated.systemTotalUnits)
        XCTAssertNil(migrated.systemReportedSuccess)
        XCTAssertEqual(migrated.retrySafety, "explicitFreshRequestOnly")
        try coordinator.begin(migrated) {}
        try coordinator.progress(90, total: 100, id: "old")
        coordinator.finish(.completed, id: "old")
        XCTAssertEqual(coordinator.active?.verifiedUnits, 0)
        try coordinator.progress(10, total: 100, id: "new")
        XCTAssertEqual(coordinator.active?.verifiedUnits, 10)
    }
    func testTypedFailureSurvivesRelaunchAndLateFinishCannotReplaceIt() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        try coordinator.begin(BackgroundOperationRecord(id: "limited", capability: "models.remote", peerID: "peer",
            label: "Receiving response", protocolID: "limited", requestDigest: "digest", startedAt: Date())) {}
        try coordinator.progress(123, id: "limited")
        coordinator.finish(.interrupted, id: "limited", failure: .outputLimit)
        coordinator.finish(.completed, id: "limited")
        let restored = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertNil(restored.active)
        XCTAssertEqual(restored.records.last?.state, .interrupted)
        XCTAssertEqual(restored.records.last?.failure, .outputLimit)
        XCTAssertEqual(restored.records.last?.verifiedUnits, 123)
        XCTAssertNotNil(restored.records.last?.finishedAt)
    }
    func testUnknownStoreVersionIsPreserved() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("operations-v1.json")
        let bytes = Data("{\"version\":2,\"value\":[]}".utf8)
        try bytes.write(to: url)
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertFalse(coordinator.canWrite)
        XCTAssertEqual(try Data(contentsOf: url), bytes)
    }
    func testCompletedTurnIdempotenceAndConflict() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = MobileChatStore(directory: directory)
        let turn = MobileChatTurn(id: "request", userID: "u", assistantID: "a", peerID: "p", preset: "normal",
            user: "2+2", answer: "4", createdAt: Date())
        try store.append(turn); try store.append(turn)
        XCTAssertEqual(MobileChatStore(directory: directory).turns.count, 1)
        XCTAssertThrowsError(try store.append(MobileChatTurn(id: "request", userID: "u", assistantID: "a",
            peerID: "p", preset: "normal", user: "2+2", answer: "5", createdAt: Date())))
    }
    func testClearingChatRemovesOnlyThatComputersTurns() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = MobileChatStore(directory: directory)
        for (id, peer) in [("one", "p"), ("two", "q"), ("three", "p")] {
            try store.append(MobileChatTurn(id: id, userID: id + "u", assistantID: id + "a", peerID: peer, preset: "normal",
                user: "question", answer: "answer", createdAt: Date()))
        }
        try store.removeTurns(peerID: "p")
        XCTAssertEqual(store.turns.map(\.id), ["two"])
        XCTAssertEqual(MobileChatStore(directory: directory).turns.map(\.id), ["two"])
        try store.removeTurns(peerID: "absent")
        XCTAssertEqual(MobileChatStore(directory: directory).turns.map(\.id), ["two"])
    }
}

@MainActor
final class CompanionProtocolTests: XCTestCase {
    func testFileRejectionsPreserveStorageAndReceiptReasonsWithoutWeakeningValidation() throws {
        let id = UUID().uuidString.lowercased()
        func rejected(_ code: String, requestID: String? = nil) -> Data {
            ConnectJSON.object(["protocol_version": .string("olive-files/1"),
                "request_id": .string(requestID ?? id), "state": .string("rejected"), "error": .string(code)]).canonical
        }
        let cases: [(String, ConnectFailure)] = [
            ("inbox_quota_exhausted", .fileInboxFull), ("unknown_transfer", .fileReceiptUnavailable),
            ("transfer_capacity_reached", .resourceBusy), ("transfer_ledger_full", .requestLedgerFull),
            ("permission_off", .remotePermissionDenied), ("permission_denied", .remotePermissionDenied),
            ("content_integrity_failed", .fileHashMismatch), ("file_io_failed", .fileTransferInterrupted)
        ]
        for (code, expected) in cases {
            XCTAssertThrowsError(try FileWire.response(rejected(code), id: id)) {
                XCTAssertEqual($0 as? ConnectFailure, expected)
            }
        }
        XCTAssertThrowsError(try FileWire.response(rejected("inbox_quota_exhausted", requestID: UUID().uuidString.lowercased()), id: id)) {
            XCTAssertEqual($0 as? ConnectFailure, .responseMalformed)
        }
        XCTAssertThrowsError(try FileWire.response(rejected("arbitrary content!"), id: id)) {
            XCTAssertEqual($0 as? ConnectFailure, .responseMalformed)
        }
    }
    func testSelectedChatDeletionUsesOrderedTombstonesWithoutResurrection() throws {
        let identity = try ConnectIdentity.generate()
        let conversation = try SyncWire.author(kind: "conversation", payload: .object(["title": .string("Synthetic selected Chat"), "project_id": .null, "created_at": .string(SyncWire.now())]), identity: identity)
        let message = try SyncWire.author(kind: "message", payload: .object(["conversation_id": .string(conversation.id), "after": .null, "role": .string("user"), "content": .string("Synthetic"), "created_at": .string(SyncWire.now())]), identity: identity)
        var value = SyncSnapshot(); try MobileSyncStore.put(conversation, in: &value); try MobileSyncStore.put(message, in: &value)
        try MobileSyncStore.tombstoneConversation(conversation, identity: identity, in: &value)
        XCTAssertTrue(value.records[conversation.id]!.deleted); XCTAssertTrue(value.records[message.id]!.deleted)
        XCTAssertLessThan(value.sequence[message.id]!, value.sequence[conversation.id]!)
        XCTAssertEqual(value.messageParents[message.id], conversation.id)
        XCTAssertEqual(try MobileSyncStore.apply(message, peer: identity.publicIdentity.deviceID, in: &value), "stale")
        XCTAssertThrowsError(try MobileSyncStore.tombstoneConversation(conversation, identity: identity, in: &value))
        XCTAssertTrue(value.records[message.id]!.deleted)
    }
    func testRemoteOnlyConflictReceiptPersistsUntilDominatingResolution() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let identity = try ConnectIdentity.generate(), peer = UUID().uuidString.lowercased(), key = peer + ":tasks"
        let record = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Synthetic conflict"), identity: identity)
        var snapshot = SyncSnapshot(); try MobileSyncStore.put(record, in: &snapshot)
        MobileSyncStore.recordOutcomes([.string("conflict")], batch: [record], incoming: [], key: key, in: &snapshot)
        let store = MobileSyncStore(directory: directory); try store.commit(snapshot)
        snapshot = MobileSyncStore(directory: directory).snapshot
        MobileSyncStore.recordOutcomes([], batch: [], incoming: [], key: key, in: &snapshot)
        XCTAssertTrue(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: snapshot))
        MobileSyncStore.recordOutcomes([.string("duplicate")], batch: [record], incoming: [record], key: key, in: &snapshot)
        XCTAssertTrue(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: snapshot))
        let resolved = try SyncWire.author(kind: "task", id: record.id, payload: SyncPayload.task(title: "Reviewed resolution"), parents: [record], identity: identity)
        MobileSyncStore.recordOutcomes([], batch: [], incoming: [resolved], key: key, in: &snapshot)
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: snapshot))
    }
    func testSyncRecoveryPreservesOriginalAndDoesNotReplay() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("sync-v1.json"), original = Data("{unreadable synthetic store".utf8)
        try original.write(to: url)
        let store = MobileSyncStore(directory: directory)
        XCTAssertFalse(store.available); XCTAssertThrowsError(try store.commit(SyncSnapshot()))
        try store.recover()
        XCTAssertTrue(store.available); XCTAssertTrue(store.snapshot.records.isEmpty)
        XCTAssertTrue(store.snapshot.cursors.isEmpty); XCTAssertTrue(store.snapshot.acknowledged.isEmpty)
        let archived = try FileManager.default.contentsOfDirectory(at: directory.appendingPathComponent("Recovery"), includingPropertiesForKeys: nil)
        XCTAssertEqual(archived.count, 1); XCTAssertEqual(try Data(contentsOf: archived[0]), original)
        XCTAssertTrue(MobileSyncStore(directory: directory).available)
        try store.recover(); XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: directory.appendingPathComponent("Recovery").path).count, 1)
    }
    func testRecoveryRefusesUnboundedArchivesWithoutChangingOriginal() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = ProtectedStore<[String]>(url: directory.appendingPathComponent("fixture.json"), maximumBytes: 1000)
        try store.save(["original"])
        for _ in 0..<4 { try store.archiveAndReplace(with: ["fresh"]) }
        let before = try Data(contentsOf: store.url)
        XCTAssertThrowsError(try store.archiveAndReplace(with: ["must not replace"]))
        XCTAssertEqual(try Data(contentsOf: store.url), before)
    }
    func testExportCleanupKeepsVerifiedInboxAndExternalFiles() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        let exports = directory.appendingPathComponent("Exports")
        try FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
        let verified = try staging.path(UUID().uuidString.lowercased(), "bin")
        try Data("verified".utf8).write(to: verified)
        try Data("temporary export".utf8).write(to: exports.appendingPathComponent("fixture.txt"))
        try FileManager.default.createSymbolicLink(at: exports.appendingPathComponent("link"), withDestinationURL: verified)
        try staging.clearExportCopies()
        XCTAssertEqual(try Data(contentsOf: verified), Data("verified".utf8))
        XCTAssertTrue(FileManager.default.fileExists(atPath: exports.appendingPathComponent("link").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: exports.appendingPathComponent("fixture.txt").path))
    }
    private func calendarFixture(_ fields: [String: ConnectJSON] = [:]) -> ConnectJSON {
        var base: [String: ConnectJSON] = ["calendar_id": .string(String(repeating: "a", count: 32)), "title": .string("Synthetic event"), "description": .string(""), "location": .string(""),
            "start": .string("2026-03-07T02:30:00-05:00"), "end": .string("2026-03-07T03:30:00-05:00"), "timezone": .string("America/New_York"), "all_day": .bool(false),
            "recurrence": .string("FREQ=DAILY;COUNT=3"), "exceptions": .object([:]), "contact_ids": .array([]), "project_id": .string(""), "status": .string("confirmed"), "transparent": .bool(false), "unsupported": .array([]), "original_ics": .string("")]
        base.merge(fields) { _, new in new }; return .object(base)
    }
    func testCalendarDSTCountExceptionsAndReminders() throws {
        let event = calendarFixture(), after = try SyncDate.parse("2026-03-01T00:00:00Z", zoned: true), before = try SyncDate.parse("2026-03-20T00:00:00Z", zoned: true)
        try SyncPayload.validate(kind: "event", value: event)
        let instances = try SyncCalendar.occurrences(event, after: after, before: before)
        XCTAssertEqual(instances.map { $0["start"].string! }, ["2026-03-07T02:30:00-05:00", "2026-03-09T02:30:00-04:00", "2026-03-10T02:30:00-04:00"])
        let invalid = calendarFixture(["exceptions": .object(["2026-03-08T02:30:00-05:00": .object(["cancelled": .bool(true)])])])
        XCTAssertThrowsError(try SyncPayload.validate(kind: "event", value: invalid))
        let reminder = ConnectJSON.object(["at": .string(""), "target_kind": .string("event"), "offset_minutes": .int(30)])
        XCTAssertEqual(try SyncCalendar.reminderTimes(reminder, target: event, after: after, before: before).count, 3)
        XCTAssertTrue(try SyncCalendar.reminderTimes(reminder, target: calendarFixture(["status": .string("cancelled")]), after: after, before: before).isEmpty)
        var task = SyncPayload.task(title: "Due task").object!; task["due"] = .string("2026-03-10"); task["timezone"] = .string("UTC")
        let taskReminder = ConnectJSON.object(["at": .string(""), "target_kind": .string("task"), "offset_minutes": .int(30)])
        XCTAssertEqual(try SyncCalendar.reminderTimes(taskReminder, target: .object(task), after: after, before: before), [try SyncDate.parse("2026-03-10T08:30:00Z", zoned: true)])
    }
    func testSignedSyncConflictStaleTombstoneAndChangedRevision() throws {
        let identity = try ConnectIdentity.generate(), other = try ConnectIdentity.generate()
        let record = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Owned fixture"), identity: identity)
        var snapshot = SyncSnapshot()
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "duplicate")
        let left = try SyncWire.author(kind: "task", id: record.id, payload: SyncPayload.task(title: "Left"), parents: [record], identity: identity)
        let right = try SyncWire.author(kind: "task", id: record.id, payload: SyncPayload.task(title: "Right"), parents: [record], identity: other)
        XCTAssertEqual(try MobileSyncStore.apply(left, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(right, peer: other.publicIdentity.deviceID, in: &snapshot), "conflict")
        XCTAssertEqual(snapshot.conflicts.count, 1)
        XCTAssertEqual(snapshot.records[record.id]?.revision, left.revision)
        let tombstone = try SyncWire.author(kind: "task", id: record.id, payload: .object([:]), deleted: true, parents: [left, right], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(tombstone, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertTrue(snapshot.conflicts.isEmpty)
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "stale")
        let resurrected = try SyncWire.author(kind: "task", id: record.id, payload: record.payload, parents: [tombstone], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(resurrected, peer: identity.publicIdentity.deviceID, in: &snapshot), "conflict")
        var changed = left.wire.object!; changed["payload"] = SyncPayload.task(title: "Tamper")
        XCTAssertThrowsError(try SignedSyncRecord(.object(changed)))
        XCTAssertTrue(snapshot.records[record.id]!.deleted)
    }
    func testUnresolvedConflictSurvivesDuplicateExchangeAndRelaunchUntilResolution() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let phone = try ConnectIdentity.generate(), desktop = try ConnectIdentity.generate()
        let peer = desktop.publicIdentity.deviceID
        let base = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Shared"), identity: phone)
        let local = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "Phone edit"), parents: [base], identity: phone)
        let remote = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "Desktop edit"), parents: [base], identity: desktop)
        var value = SyncSnapshot()
        try MobileSyncStore.put(local, in: &value)
        XCTAssertEqual(try MobileSyncStore.apply(remote, peer: peer, in: &value), "conflict")
        // A receipt and repeated version do not resolve the competing edits.
        value.acknowledged[peer + ":tasks"] = [local.revision]
        XCTAssertEqual(try MobileSyncStore.apply(local, peer: peer, in: &value), "duplicate")
        let store = MobileSyncStore(directory: directory); try store.commit(value)
        let restored = MobileSyncStore(directory: directory)
        XCTAssertTrue(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: restored.snapshot))
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "calendar", peer: peer, in: restored.snapshot))
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "tasks", peer: phone.publicIdentity.deviceID, in: restored.snapshot))
        XCTAssertEqual(restored.snapshot.records[base.id]?.payload["title"], .string("Phone edit"))
        XCTAssertEqual(restored.snapshot.conflicts.first?.incoming.payload["title"], .string("Desktop edit"))
        value = restored.snapshot
        let resolved = try SyncWire.author(kind: "task", id: base.id, payload: remote.payload, parents: [local, remote], identity: desktop)
        XCTAssertEqual(try MobileSyncStore.apply(resolved, peer: peer, in: &value), "applied")
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: value))
    }
    func testChatSelectionImmutableOrderAndDeletedPredecessor() throws {
        let identity = try ConnectIdentity.generate(), peer = identity.publicIdentity.deviceID
        let conversation = try SyncWire.author(kind: "conversation", payload: .object([
            "title": .string("Selected fixture"), "project_id": .null, "created_at": .string(SyncWire.now())]), identity: identity)
        var value = SyncSnapshot()
        XCTAssertEqual(try MobileSyncStore.apply(conversation, peer: peer, in: &value), "applied")
        func message(after: String?) throws -> SignedSyncRecord {
            try SyncWire.author(kind: "message", payload: .object(["conversation_id": .string(conversation.id),
                "after": after.map(ConnectJSON.string) ?? .null, "role": .string("user"),
                "content": .string("Owned fixture"), "created_at": .string(SyncWire.now())]), identity: identity)
        }
        let first = try message(after: nil), second = try message(after: first.id)
        XCTAssertEqual(try MobileSyncStore.apply(first, peer: peer, in: &value), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(second, peer: peer, in: &value), "applied")
        var reordered = second.payload.object!; reordered["after"] = .null
        let changed = try SyncWire.author(kind: "message", id: second.id, payload: .object(reordered), parents: [second], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(changed, peer: peer, in: &value), "conflict")
        let deleted = try SyncWire.author(kind: "message", id: first.id, payload: .object([:]), deleted: true, parents: [first], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(deleted, peer: peer, in: &value), "applied")
        XCTAssertEqual(value.messagePredecessors?[second.id], first.id)
        XCTAssertTrue(MobileSyncStore.dependency(second, in: value))
        value.selection[peer + ":" + conversation.id] = false
        XCTAssertEqual(try MobileSyncStore.apply(message(after: second.id), peer: peer, in: &value), "conflict")
    }
    func testSyncStoreAtomicReopenAndMissingDependency() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let identity = try ConnectIdentity.generate()
        let reminder = try SyncWire.author(kind: "reminder", payload: .object(["target_kind": .string("task"), "target_id": .string(UUID().uuidString.lowercased()), "at": .string(""), "offset_minutes": .int(30), "timezone": .string("UTC")]), identity: identity)
        let store = MobileSyncStore(directory: directory); var value = store.snapshot
        XCTAssertEqual(try MobileSyncStore.apply(reminder, peer: identity.publicIdentity.deviceID, in: &value), "conflict")
        XCTAssertNil(value.records[reminder.id])
        try store.commit(value)
        let restarted = MobileSyncStore(directory: directory)
        XCTAssertEqual(restarted.snapshot.conflicts.count, 1)
        XCTAssertNotNil(restarted.snapshot.receipts[reminder.revision])
    }
    func testTodayDraftRetainsOriginalRevisionAcrossLaunchWithoutApplying() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let identity = try ConnectIdentity.generate()
        let original = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Original"), identity: identity)
        let changed = SyncPayload.task(title: "Offline draft")
        let store = MobileSyncStore(directory: directory)
        try store.drafts.save(original.id, original: original, fields: changed.object)
        let restarted = MobileSyncStore(directory: directory)
        XCTAssertTrue(restarted.snapshot.records.isEmpty)
        let draft = try XCTUnwrap(restarted.drafts.get(original.id))
        XCTAssertEqual(draft.original?.revision, original.revision)
        XCTAssertEqual(try ConnectJSON.decode(draft.fields), changed)
        try restarted.drafts.save(original.id, original: nil, fields: nil)
        XCTAssertNil(try TodayDraftStore(directory: directory).get(original.id))
    }
    func testC6BoundsRawBytesAndOwnedStaging() throws {
        let source = UUID().uuidString.lowercased(), target = UUID().uuidString.lowercased(), id = UUID().uuidString.lowercased()
        let meta = try FileMetadata(name: "fixture.bin", size: 3, sha256: String(repeating: "a", count: 64), mime: "application/octet-stream")
        let req = FileWire.request(source: source, target: target, transfer: id, operation: "chunk", arguments: .object(["offset": .int(0)]))
        let bytes = Data([0, 255, 1]), decoded = try FileWire.decode(FileWire.packet(req, bytes: bytes))
        XCTAssertEqual(decoded.1, bytes)
        XCTAssertThrowsError(try FileMetadata(name: "../secret", size: 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileMetadata(name: "CON.txt", size: 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileMetadata(name: "large", size: FileWire.maximumFile + 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileWire.packet(req, bytes: Data(repeating: 0, count: 65537)))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        XCTAssertThrowsError(try staging.path("../../outside", "out"))
        let file = directory.appendingPathComponent("owned.bin"); try bytes.write(to: file)
        let copied = try staging.copySelection(file, id: id)
        XCTAssertEqual(copied.size, 3)
        XCTAssertEqual(try staging.digest(staging.path(id, "out")).1, copied.sha256)
        XCTAssertEqual(try Data(contentsOf: file), bytes)
    }
    func testC6FinalizationRehashesStoredBytesAndRefusesCollision() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        let id = UUID().uuidString.lowercased(), bytes = Data("owned fixture".utf8)
        let partial = try staging.path(id, "part"), final = try staging.path(id, "bin")
        try bytes.write(to: partial)
        let metadata = try FileMetadata(name: "fixture.bin", size: Int64(bytes.count), sha256: Data(SHA256.hash(data: bytes)).hex, mime: "application/octet-stream")
        try Data("changed bytes".utf8).write(to: partial)
        XCTAssertThrowsError(try staging.finalize(id, metadata: metadata)) { XCTAssertEqual($0 as? ConnectFailure, .fileHashMismatch) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: final.path))
        try bytes.write(to: partial)
        try Data("keep existing".utf8).write(to: final)
        XCTAssertThrowsError(try staging.finalize(id, metadata: metadata))
        XCTAssertEqual(try Data(contentsOf: final), Data("keep existing".utf8))
        try FileManager.default.removeItem(at: final)
        try staging.finalize(id, metadata: metadata)
        XCTAssertEqual(try Data(contentsOf: final), bytes)
    }
    @MainActor func testC6RelaunchInterruptsPartialTransferWithoutReplayOrDeletingVerifiedFiles() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        let peer = UUID().uuidString.lowercased(), bytes = Data("owned fixture".utf8)
        let metadata = try FileMetadata(name: "fixture.bin", size: Int64(bytes.count), sha256: Data(SHA256.hash(data: bytes)).hex, mime: "application/octet-stream")
        var partial = MobileFileReceipt(id: UUID().uuidString.lowercased(), peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date())
        partial.state = "transferring"; partial.received = 3
        var verified = MobileFileReceipt(id: UUID().uuidString.lowercased(), peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date())
        verified.state = "completed"; verified.received = metadata.size
        try Data(bytes.prefix(3)).write(to: staging.path(partial.id, "part"))
        try bytes.write(to: staging.path(verified.id, "bin"))
        let unrelated = directory.appendingPathComponent("keep.txt"); try bytes.write(to: unrelated)
        let store = ProtectedStore<[MobileFileReceipt]>(url: directory.appendingPathComponent("receipts-v1.json"), maximumBytes: 8_000_000)
        try store.save([partial, verified])
        let model = FilesModel(session: nil, background: nil, directory: directory)
        XCTAssertTrue(model.available)
        XCTAssertEqual(model.receipts.first(where: { $0.id == partial.id })?.state, "interrupted")
        XCTAssertFalse(FileManager.default.fileExists(atPath: try staging.path(partial.id, "part").path))
        await model.cancel(partial.id); await model.cancel(verified.id)
        XCTAssertEqual(try store.load()?.map(\.state), ["interrupted", "completed"])
        XCTAssertEqual(try Data(contentsOf: staging.path(verified.id, "bin")), bytes)
        XCTAssertEqual(try Data(contentsOf: unrelated), bytes)
    }
    func testStudioCancelledBeforeAdmissionDoesNotConnectOrRetry() async throws {
        let transport = ConnectTransport(endpoint: .hostPort(host: "127.0.0.1", port: 9))
        let request = try StudioWire.request(source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased(),
            operation: "build", workspace: UUID().uuidString.lowercased(), revision: 1)
        do {
            _ = try await StudioWire.exchange(request, channel: transport, cancelled: { true })
            XCTFail("Cancelled Studio request must not reach the transport")
        } catch { XCTAssertEqual(error as? ConnectFailure, .requestCancelled) }
    }
    func testStudioReadHashAndStaleSaveResponse() throws {
        let source = UUID().uuidString.lowercased(), target = UUID().uuidString.lowercased(), workspace = UUID().uuidString.lowercased()
        let req = try StudioWire.request(source: source, target: target, operation: "read", workspace: workspace, revision: 1, arguments: .object(["path": .string("main.py")]))
        let response = ConnectJSON.object(["protocol_version": .string("olive-studio/1"), "request_id": req["request_id"], "error": .null,
            "result": .object(["path": .string("main.py"), "text": .string("changed"), "revision": .string(String(repeating: "a", count: 64))])])
        XCTAssertThrowsError(try StudioWire.response(response.canonical, request: req))
        XCTAssertThrowsError(try StudioWire.request(source: source, target: target, operation: "terminal", workspace: workspace, revision: 1))
        XCTAssertThrowsError(try StudioWire.path(.string("../secret")))
        XCTAssertEqual(StudioWire.failure("revision_conflict"), .studioRevisionStale)
        XCTAssertEqual(StudioWire.failure("device_revoked"), .deviceRevoked)
        XCTAssertEqual(InferenceWire.failure("device_revoked"), .deviceRevoked)
        XCTAssertEqual(InferenceWire.failure("connection_lost"), .connectionLost)
        XCTAssertThrowsError(try ConnectJSON.decode(Data("1.5".utf8)))
        XCTAssertEqual(try ConnectJSON.decode(Data("1.5".utf8), allowDecimals: true), .decimal("1.5"))
        for value in ["1e999", "1.e2", "1.2.3", "NaN"] { XCTAssertThrowsError(try ConnectJSON.decode(Data(value.utf8), allowDecimals: true)) }
    }
    func testNotificationLabelsContainNoContent() {
        XCTAssertEqual(CompletionNotifications.message(for: "models.remote"), "Response ready")
        XCTAssertEqual(CompletionNotifications.message(for: "files.receive"), "File transfer complete")
        XCTAssertEqual(CompletionNotifications.message(for: "studio.test"), "Studio operation finished")
    }
}
