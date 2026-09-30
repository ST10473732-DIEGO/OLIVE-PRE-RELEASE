import Foundation
import CoreGraphics

// OLIVE Draw interop harness: the real Swift DrawEngine (SQLite store, replica
// rules, olive-draw/1 codec, asset import, CoreGraphics renderer), driven by
// tests/test_draw_phone_engine.py over JSON lines. Every sync exchange carries
// real olive-draw/1 request/response bytes produced and parsed by each side's
// own production codec. No socket, UI or phone profile is involved.

/// Hands one async result back to the synchronous harness loop across a
/// semaphore; written once before `signal`, read once after `wait` (harness only).
private final class HarnessResult<T>: @unchecked Sendable { var value: Result<T, Error>? }

private func blocking<T>(_ body: @escaping @Sendable () async throws -> T) throws -> T {
    let semaphore = DispatchSemaphore(value: 0)
    let box = HarnessResult<T>()
    Task.detached {
        do { box.value = .success(try await body()) } catch { box.value = .failure(error) }
        semaphore.signal()
    }
    semaphore.wait()
    return try box.value!.get()
}

private func emit(_ value: ConnectJSON) {
    print(String(decoding: value.canonical, as: UTF8.self)); fflush(stdout)
}

private func summaryJSON(_ s: DrawSummary) -> ConnectJSON {
    .object(["drawing_id": .string(s.id), "title": .string(s.title), "width": .int(Int64(s.width)), "height": .int(Int64(s.height)),
             "background": .string(s.background), "trashed": .bool(s.trashed), "status": .string(s.status),
             "op_count": .int(Int64(s.opCount)), "schema_version": .int(Int64(s.schemaVersion))])
}

private func editJSON(_ edit: DrawEdit) -> ConnectJSON {
    .object(["record": edit.record?.json ?? .null, "cursor": edit.cursor.map { .int($0) } ?? .null,
             "undo": .int(Int64(edit.undo)), "redo": .int(Int64(edit.redo))])
}

func runDrawHarness(directory: URL) {
    var engine: DrawEngine?
    var deviceID = ""
    var allowed = Set<String>()
    func boot(_ id: String) {
        engine = nil
        engine = DrawEngine(directory: directory, deviceID: id)
        deviceID = id
    }
    while let line = readLine() {
        var reply: [String: ConnectJSON] = [:]
        do {
            let message = try ConnectJSON.decode(Data(line.utf8), limit: 64_000_000, allowDecimals: true)
            reply["id"] = message["id"]
            let args = message["args"].array ?? []
            func text(_ i: Int) throws -> String { try args[i].text() }
            let command = message["cmd"].string ?? ""
            if command == "boot" { boot(try text(0)); reply["result"] = .bool(true); emit(.object(reply)); continue }
            guard let engine else { throw DrawError("not_booted") }
            let local = deviceID, permitted = allowed
            switch command {
            case "runtime":
                // Proof for the Python tests that this is the Swift engine, not a stand-in.
                let url = try blocking { await engine.storeURL }
                reply["result"] = .object(["runtime": .string("swift-draw-engine"), "database": .string(url?.path ?? ""),
                                           "available": .bool(try blocking { await engine.available })])
            case "allow":
                if args[1].boolean == true { allowed.insert(try text(0)) } else { allowed.remove(try text(0)) }
                reply["result"] = .bool(true)
            case "create":
                let title = try text(0), width = Int(args[1].integer ?? 0), height = Int(args[2].integer ?? 0), bg = try text(3)
                reply["result"] = summaryJSON(try blocking { try await engine.create(title: title, width: width, height: height, background: bg) })
            case "get":
                let did = try text(0)
                reply["result"] = summaryJSON(try blocking { try await engine.summary(did) })
            case "list":
                let trash = args.first?.string == "trash"
                reply["result"] = .array(try blocking { try await engine.list(trash: trash) }.map(summaryJSON))
            case "append":
                let did = try text(0), op = try DrawOp(json: args[1])
                reply["result"] = editJSON(try blocking { try await engine.append(did, op) })
            case "undo", "redo":
                let did = try text(0)
                reply["result"] = editJSON(try blocking { command == "undo" ? try await engine.undo(did) : try await engine.redo(did) })
            case "rename":
                let did = try text(0), title = try text(1)
                reply["result"] = summaryJSON(try blocking { try await engine.rename(did, title: title) })
            case "trash", "restore":
                let did = try text(0)
                reply["result"] = summaryJSON(try blocking { command == "trash" ? try await engine.trash(did) : try await engine.restore(did) })
            case "duplicate":
                let did = try text(0)
                reply["result"] = summaryJSON(try blocking { try await engine.duplicate(did) })
            case "purge":
                let did = try text(0)
                try blocking { try await engine.purge(did) }; reply["result"] = .bool(true)
            case "is_purged":
                let did = try text(0)
                reply["result"] = .bool(try blocking { try await engine.isPurged(did) })
            case "ops":
                let did = try text(0)
                reply["result"] = .array(try blocking { try await engine.visibleOperations(did) }.map(\.json))
            case "state":
                // Canonical, comparable state (same shape as tests/draw_sync_fixture.py).
                let did = try text(0)
                let (summary, ops, history) = try blocking { (try await engine.summary(did), try await engine.visibleOperations(did), try await engine.history(did)) }
                reply["result"] = .object(["title": .string(summary.title), "trashed": .bool(summary.trashed),
                    "width": .int(Int64(summary.width)), "height": .int(Int64(summary.height)),
                    "background": .string(ops.effectiveBackground(summary.background)), "ops": .array(ops.map { .string($0.id) }),
                    "undo": .int(Int64(history.undo)), "redo": .int(Int64(history.redo))])
            case "order":
                let did = try text(0)
                reply["result"] = .array(try blocking { try await engine.operationOrder(did) }.map { .string($0) })
            case "apply":
                // Direct record insertion (conformance in random arrival orders).
                let records = args[0].array ?? [], source = args.count > 1 ? try text(1) : ""
                reply["result"] = .array(try blocking { try await engine.insertRecords(records, source: source) }.map { .string($0) })
            case "since":
                let did = try text(0), after = args.count > 1 ? args[1].integer ?? 0 : 0
                let page = try blocking { try await engine.since(did, after: after) }
                reply["result"] = .object(["records": .array(page.records.map(\.json)), "cursor": .int(page.cursor), "more": .bool(page.more),
                    "missing_assets": .array(page.missingAssets.map { .string($0) })])
            case "handle":
                // Receiving side exactly as the app's Connect frame-15 handler.
                let peer = try text(0), raw = Data(try text(1).utf8)
                let allowedNow = permitted.contains(peer)
                let response = try blocking { await DrawWire.receive(engine: engine, raw: raw, peer: peer, local: local, permitted: allowedNow, now: DrawWire.now()) }
                reply["result"] = .string(String(decoding: response, as: UTF8.self))
            case "pump":
                // Sending side: each request goes to Python on stdout; its raw answer comes back on stdin.
                let peer = try text(0), hello = args.count > 1 && args[1].boolean == true
                let send = DrawWire.sender(local: local, peer: peer, clock: { DrawWire.now() }) { _, raw in
                    emit(.object(["send": .string(String(decoding: raw, as: UTF8.self))]))
                    guard let answer = readLine(), let value = try? ConnectJSON.decode(Data(answer.utf8), limit: 16_000_000, allowDecimals: true) else {
                        throw DrawProtocol.Failure("malformed_message")
                    }
                    if let error = value["error"].string { throw HarnessTransportError(code: error) }
                    return Data((value["response"].string ?? "").utf8)
                }
                do { reply["result"] = .string(try blocking { try await engine.pump(peer: peer, hello: hello, send: send) }) }
                catch let failure as HarnessTransportError { reply["error"] = .string(failure.code) }
                catch let failure as DrawProtocol.Failure { reply["error"] = .string(failure.code) }
            case "pending":
                let peer = try text(0)
                reply["result"] = .int(Int64(try blocking { try await engine.pending(peer) }))
            case "wants":
                reply["result"] = .array(try blocking { try await engine.wants() }.map { .string($0) })
            case "pending_assets":
                reply["result"] = .int(Int64(try blocking { try await engine.pendingAssets() }))
            case "staged":
                reply["result"] = .int(Int64(try blocking { await engine.stagedTransfers }))
            case "peer":
                let peer = try text(0)
                let record = try blocking { try await engine.peer(peer) }
                reply["result"] = .object(["acked_seq": .int(record.ackedSeq), "peer_epoch": record.peerEpoch.map { .string($0) } ?? .null])
            case "epoch":
                reply["result"] = .string(try blocking { try await engine.epoch() })
            case "renew_epoch":
                try blocking { try await engine.renewEpochForRestore() }; reply["result"] = .bool(true)
            case "import":
                let did = try text(0)
                guard let source = Data(base64Encoded: try text(1)) else { throw DrawError("invalid_image") }
                let summary = try blocking { try await engine.summary(did) }
                let imported = try DrawAssets.canonicalize(source, canvasWidth: summary.width, canvasHeight: summary.height)
                let edit = try blocking { try await engine.addImage(did, imported) }
                reply["result"] = .object(["asset_id": .string(imported.info.assetID), "edit": editJSON(edit),
                    "mime": .string(imported.info.mime), "width": .int(Int64(imported.width)), "height": .int(Int64(imported.height))])
            case "asset":
                let id = try text(0)
                reply["result"] = try blocking { try await engine.assetData(id) }.map { .string($0.base64EncodedString()) } ?? .null
            case "store_asset":
                guard let data = Data(base64Encoded: try text(0)) else { throw DrawError("invalid_image") }
                let info = try blocking { try await engine.storeAsset(data) }
                reply["result"] = .string(info.assetID)
            case "render", "export":
                // Document-resolution flatten by the phone renderer (PNG, or JPEG for export).
                let did = try text(0), jpeg = command == "export" && args.count > 1 && args[1].string == "jpeg"
                let (summary, ops) = try blocking { (try await engine.summary(did), try await engine.visibleOperations(did)) }
                var images: [String: CGImage] = [:], missing: [String] = []
                for asset in Set(ops.compactMap(\.assetID)) {
                    if let data = try blocking({ try await engine.assetData(asset) }), let image = DrawAssets.decode(data) { images[asset] = image }
                    else { missing.append(asset) }
                }
                if command == "export" && !missing.isEmpty { throw DrawError("asset_not_found") }
                guard let image = DrawRender.rasterize(ops, width: summary.width, height: summary.height, background: ops.effectiveBackground(summary.background),
                                                       jpeg: jpeg, images: { images[$0] }),
                      let bytes = DrawRender.encode(image, jpeg: jpeg) else { throw DrawError("draw_unavailable") }
                reply["result"] = .object(["data": .string(bytes.base64EncodedString()), "missing": .array(missing.sorted().map { .string($0) })])
            case "fail_commits":
                let count = Int(args.first?.integer ?? 1)
                try blocking { await engine.failNextCommits(count) }; reply["result"] = .bool(true)
            default:
                throw DrawError("unknown_command")
            }
        } catch let error as DrawError { reply["error"] = .string(error.code) }
        catch let error as DrawFormatError { reply["error"] = .string(error.code) }
        catch let error as DrawAssets.Failure { reply["error"] = .string(error.code) }
        catch let error as DrawProtocol.Failure { reply["error"] = .string(error.code) }
        catch { reply["error"] = .string(String(describing: error)) }
        emit(.object(reply))
    }
}

private struct HarnessTransportError: Error { let code: String }
