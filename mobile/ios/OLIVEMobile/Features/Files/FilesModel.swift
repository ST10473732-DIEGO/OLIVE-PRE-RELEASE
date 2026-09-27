import Foundation
import Observation
import CryptoKit
import UIKit

struct MobileFileReceipt: Codable, Identifiable {
    let id: String
    let peerID: String
    let incoming: Bool
    let metadata: FileMetadata
    let created: Date
    var touched: Date
    var received: Int64 = 0
    var state = "offered"
}

@MainActor @Observable
final class FilesModel {
    private let session: ConnectSession?
    private let background: BackgroundWorkCoordinator?
    private let store: ProtectedStore<[MobileFileReceipt]>
    let staging: FileStaging
    private(set) var receipts: [MobileFileReceipt] = []
    private(set) var notice = ""
    private(set) var preparing = false
    private(set) var available = true
    private var pendingCompletion: [String: String] = [:]
    private var hashes: [String: SHA256] = [:]
    private var timer: Task<Void, Never>?
    private var bound = UUID()
    private var arrivals: [Date] = []
    var recent: [MobileFileReceipt] { Array(receipts.suffix(100).reversed()) }
    init(session: ConnectSession?, background: BackgroundWorkCoordinator?, directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion/Files")) {
        self.session = session; self.background = background
        staging = FileStaging(directory: directory)
        store = ProtectedStore(url: directory.appendingPathComponent("receipts-v1.json"), maximumBytes: 8_000_000)
        do {
            try staging.prepare(); receipts = try store.load() ?? []
            guard receipts.count <= 10000 else { throw ConnectFailure.localStorageUnavailable }
            for i in receipts.indices {
                _ = try staging.path(receipts[i].id, "part")
                _ = try ConnectJSON.string(receipts[i].peerID).uuid()
                _ = try FileMetadata(receipts[i].metadata.wire)
                guard FileWire.states.contains(receipts[i].state), (0...receipts[i].metadata.size).contains(receipts[i].received),
                      receipts[i].state != "completed" || receipts[i].received == receipts[i].metadata.size else { throw ConnectFailure.localStorageUnavailable }
                if !FileWire.terminal.contains(receipts[i].state) { receipts[i].state = "interrupted" }
            }
            try store.save(receipts)
            for file in try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) {
                guard UUID(uuidString: file.deletingPathExtension().lastPathComponent)?.uuidString.lowercased() == file.deletingPathExtension().lastPathComponent else { continue }
                let keep = file.pathExtension == "bin" && receipts.contains { $0.id == file.deletingPathExtension().lastPathComponent && $0.incoming && $0.state == "completed" }
                if ["part", "out", "bin"].contains(file.pathExtension), !keep { try FileManager.default.removeItem(at: file) }
            }
        } catch { available = false; notice = ConnectFailure.localStorageUnavailable.localizedDescription }
    }
    private func put(_ row: MobileFileReceipt) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        var next = receipts
        if let index = next.firstIndex(where: { $0.id == row.id }) { next[index] = row }
        else { guard next.count < 10000 else { throw ConnectFailure.requestLedgerFull }; next.append(row) }
        try store.save(next); receipts = next
    }
    private func reserve(_ size: Int64, incoming: Bool, peer: String) throws {
        let active = receipts.filter { !FileWire.terminal.contains($0.state) }
        guard active.count < 4, active.filter({ $0.peerID == peer }).count < 2 else { throw ConnectFailure.resourceBusy }
        let used = receipts.filter { $0.incoming == incoming && (!FileWire.terminal.contains($0.state) || incoming && $0.state == "completed") }.reduce(Int64(0)) { $0 + $1.metadata.size }
        guard used + size <= (incoming ? 256 : 128) * 1024 * 1024 else { throw ConnectFailure.localStorageUnavailable }
        try staging.capacity(size)
    }
    func bind(channel: ConnectTransport, local: String, peer: String) async {
        let token = UUID(); bound = token
        await channel.setInbound({ [weak self] frame in
            guard let self else { throw ConnectFailure.peerOffline }
            return try await self.receive(frame, local: local, peer: peer, token: token)
        }, delivered: { [weak self] frame in await self?.delivered(frame) })
        timer?.cancel()
        timer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self, self.bound == token, !Task.isCancelled else { return }
                for row in self.receipts where !FileWire.terminal.contains(row.state) {
                    let idle = ["offered", "awaiting_approval"].contains(row.state) ? 120.0 : 30.0
                    if Date().timeIntervalSince(row.touched) > idle || Date().timeIntervalSince(row.created) > 600 {
                        self.end(row.id, state: "interrupted")
                    }
                }
            }
        }
    }
    private func delivered(_ frame: ConnectFrame) {
        guard let reply = try? ConnectJSON.decode(frame.payload, limit: 16384),
              let request = reply["request_id"].string, let id = pendingCompletion.removeValue(forKey: request) else { return }
        background?.finish(.completed, id: id); session?.finishBackgroundWork()
    }
    func invalidate() {
        bound = UUID(); timer?.cancel(); timer = nil
        for id in pendingCompletion.values { background?.finish(.interrupted, id: id) }
        pendingCompletion.removeAll()
        for row in receipts where !FileWire.terminal.contains(row.state) { end(row.id, state: "interrupted") }
    }
    private func end(_ id: String, state: String, deferCompletion: Bool = false) {
        guard var row = receipts.first(where: { $0.id == id }), !FileWire.terminal.contains(row.state) else { return }
        row.state = state; row.touched = Date()
        do { try put(row) } catch { available = false; notice = ConnectFailure.localStorageUnavailable.localizedDescription }
        hashes[id] = nil
        for suffix in ["part", "out"] { if let path = try? staging.path(id, suffix) { try? FileManager.default.removeItem(at: path) } }
        if !deferCompletion, background?.active?.id == id {
            background?.finish(state == "completed" ? .completed : state == "cancelled" ? .cancelled : .interrupted)
            // Defer closing until the incoming completion response has been sent.
            if row.incoming { Task { try? await Task.sleep(for: .seconds(1)); if self.background?.active == nil { self.session?.finishBackgroundWork() } } }
            else { session?.finishBackgroundWork() }
        }
    }
    func select(_ url: URL) async {
        guard !preparing, let peer = session?.selectedID else { notice = ConnectFailure.peerOffline.localizedDescription; return }
        preparing = true; defer { preparing = false }
        let id = UUID().uuidString.lowercased(), staging = self.staging
        do {
            try reserve(0, incoming: false, peer: peer)
            let meta = try await Task.detached { try staging.copySelection(url, id: id) }.value
            try reserve(meta.size, incoming: false, peer: peer)
            try put(MobileFileReceipt(id: id, peerID: peer, incoming: false, metadata: meta, created: Date(), touched: Date()))
            notice = "Review the selected file, then Send."
        } catch { if let path = try? staging.path(id, "out") { try? FileManager.default.removeItem(at: path) }; notice = error is ConnectFailure ? error.localizedDescription : ConnectFailure.localStorageUnavailable.localizedDescription }
    }
    private func exchange(_ row: MobileFileReceipt, operation: String, args: ConnectJSON = .object([:]), bytes: Data = Data(), context: (ConnectTransport, ConnectIdentity, TrustedConnectPeer)) async throws -> ConnectJSON {
        let (channel, identity, peer) = context
        guard peer.id == row.peerID else { throw ConnectFailure.peerOffline }
        let request = FileWire.request(source: identity.publicIdentity.deviceID, target: peer.id, transfer: row.id, operation: operation, arguments: args)
        return try FileWire.response(await channel.exchangeFrame(kind: 7, id: request["request_id"].uuid(), payload: FileWire.packet(request, bytes: bytes)), id: request["request_id"].uuid())
    }
    func send(_ id: String) async {
        guard let session, var row = receipts.first(where: { $0.id == id && !$0.incoming && $0.state == "offered" }) else { return }
        do {
            let context = try await session.context()
            guard context.2.id == row.peerID else { throw ConnectFailure.peerOffline }
            let offer = FileWire.request(source: context.1.publicIdentity.deviceID, target: row.peerID, transfer: id, operation: "offer", arguments: row.metadata.wire)
            try background?.begin(BackgroundOperationRecord(id: id, capability: "files.receive", peerID: row.peerID,
                label: "Sending file", protocolID: id, requestDigest: offer.digest, startedAt: Date(), totalUnits: row.metadata.size, scope: ["name": row.metadata.name, "sha256": row.metadata.sha256, "direction": "outgoing"])) { [weak self] in await self?.cancel(id) }
            row.state = "awaiting_approval"; try put(row)
            let deadline = ContinuousClock.now.advanced(by: .seconds(120))
            while true {
                guard receipts.first(where: { $0.id == id })?.state == "awaiting_approval" else { throw ConnectFailure.fileTransferCancelled }
                let r = try FileWire.response(await context.0.exchangeFrame(kind: 7, id: offer["request_id"].uuid(), payload: FileWire.packet(offer)), id: offer["request_id"].uuid())
                if r["state"] == .string("accepted"), r["received_size"] == .int(0) { break }
                guard r["state"] == .string("awaiting_approval"), ContinuousClock.now < deadline else { throw ConnectFailure.fileTransferInterrupted }
                try await Task.sleep(for: .seconds(1))
            }
            row.state = "transferring"; row.touched = Date(); try put(row)
            let handle = try FileHandle(forReadingFrom: staging.path(id, "out")); defer { try? handle.close() }
            while row.received < row.metadata.size {
                guard receipts.first(where: { $0.id == id })?.state == "transferring" else { throw ConnectFailure.fileTransferCancelled }
                guard let bytes = try handle.read(upToCount: 65536), !bytes.isEmpty else { throw ConnectFailure.fileTransferInterrupted }
                let r = try await exchange(row, operation: "chunk", args: .object(["offset": .int(row.received)]), bytes: bytes, context: context)
                let next = row.received + Int64(bytes.count)
                guard r == .object(["state": .string("transferring"), "received_size": .int(next)]) else { throw ConnectFailure.fileTransferInterrupted }
                // Cancellation must not be undone by a late acknowledgement.
                guard receipts.first(where: { $0.id == id })?.state == "transferring" else { throw ConnectFailure.fileTransferCancelled }
                row.received = next; row.touched = Date(); try put(row); try background?.progress(next, total: row.metadata.size, id: id)
            }
            let r = try await exchange(row, operation: "complete", context: context)
            guard r == .object(["state": .string("completed"), "received_size": .int(row.metadata.size)]) else { throw ConnectFailure.fileTransferInterrupted }
            guard receipts.first(where: { $0.id == id })?.state == "transferring" else { throw ConnectFailure.fileTransferCancelled }
            end(id, state: "completed"); notice = "Transfer verified by computer."
        } catch { end(id, state: "interrupted"); notice = error is ConnectFailure ? error.localizedDescription : ConnectFailure.fileTransferInterrupted.localizedDescription }
    }
    func accept(_ id: String) {
        guard UIApplication.shared.applicationState == .active, var row = receipts.first(where: { $0.id == id && $0.incoming && $0.state == "awaiting_approval" }) else { return }
        do {
            try background?.begin(BackgroundOperationRecord(id: id, capability: "files.receive", peerID: row.peerID,
                label: "Receiving file", protocolID: id, requestDigest: row.metadata.wire.digest, startedAt: Date(), totalUnits: row.metadata.size, scope: ["name": row.metadata.name, "sha256": row.metadata.sha256, "direction": "incoming"])) { [weak self] in await self?.cancel(id) }
            try Data().write(to: staging.path(id, "part"), options: [.withoutOverwriting, .completeFileProtectionUntilFirstUserAuthentication])
            hashes[id] = SHA256(); row.state = "accepted"; row.touched = Date(); try put(row)
        } catch { end(id, state: "failed"); notice = error.localizedDescription }
    }
    func cancel(_ id: String) async {
        guard let row = receipts.first(where: { $0.id == id }), !FileWire.terminal.contains(row.state) else { return }
        end(id, state: "cancelled")
        if let context = try? await session?.context() { _ = try? await exchange(row, operation: "cancel", context: context) }
    }
    func reconcile(_ id: String) async {
        guard let row = receipts.first(where: { $0.id == id && !$0.incoming }), let session else { return }
        do {
            let r = try await exchange(row, operation: "status", context: session.context())
            notice = "Computer receipt: " + (r["state"].string ?? "Unknown")
            if r["state"] == .string("completed"), r["received_size"] == .int(row.metadata.size) {
                var verified = row; verified.state = "completed"; verified.received = row.metadata.size; try put(verified)
            }
        } catch { notice = error.localizedDescription }
    }
    func exportURL(_ id: String) throws -> URL {
        guard let row = receipts.first(where: { $0.id == id && $0.incoming && $0.state == "completed" }) else { throw ConnectFailure.fileSaveRequired }
        let url = try staging.path(id, "bin"), checked = try staging.digest(url)
        guard checked.0 == row.metadata.size, checked.1 == row.metadata.sha256 else { throw ConnectFailure.fileHashMismatch }
        // Only an explicit export creates this bounded, app-owned copy. The
        // system picker controls the external destination; remote names never do.
        let exports = staging.directory.appendingPathComponent("Exports")
        try FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
        for old in try FileManager.default.contentsOfDirectory(at: exports, includingPropertiesForKeys: nil) {
            // Files in this dedicated directory are created by this method only.
            try FileManager.default.removeItem(at: old)
        }
        let copy = exports.appendingPathComponent(row.metadata.name)
        try FileManager.default.copyItem(at: url, to: copy)
        return copy
    }
    private func receive(_ frame: ConnectFrame, local: String, peer: String, token: UUID) throws -> ConnectFrame {
        guard token == bound, session?.connected == true, session?.selectedID == peer else { throw ConnectFailure.peerOffline }
        if frame.kind == 5 {
            let request = try ConnectJSON.decode(frame.payload, limit: 256000)
            let id = try request["request_id"].uuid()
            guard request["source_device_id"] == .string(peer), request["target_device_id"] == .string(local), request["protocol_version"] == .string("olive-sync/1") else { throw ConnectFailure.identityMismatch }
            return ConnectFrame(kind: 6, payload: ConnectJSON.object(["protocol_version": .string("olive-sync/1"), "request_id": .string(id), "state": .string("rejected"), "error": .string("permission_off")]).canonical)
        }
        arrivals.removeAll { Date().timeIntervalSince($0) >= 60 }
        guard arrivals.count < 2400 else { throw ConnectFailure.rateLimited }
        arrivals.append(Date())
        guard frame.kind == 7 else { throw ConnectFailure.capabilityUnavailable }
        let (request, bytes) = try FileWire.decode(frame.payload)
        let id = try request["transfer_id"].uuid(), requestID = try request["request_id"].uuid()
        guard request["source_device_id"] == .string(peer), request["target_device_id"] == .string(local) else { throw ConnectFailure.identityMismatch }
        var response: ConnectJSON
        do {
            let now = Int64(Date().timeIntervalSince1970)
            guard try request["expires_at"].number(0...253402300799) > now, try request["timestamp"].number(0...253402300799) <= now + 30 else { throw ConnectFailure.requestTimeout }
            let operation = try request["operation"].text()
            if operation == "offer" {
                let metadata = try FileMetadata(request["arguments"])
                if let existing = receipts.first(where: { $0.id == id }) {
                    guard existing.peerID == peer, existing.incoming, existing.metadata == metadata else { throw ConnectFailure.responseMalformed }
                } else {
                    guard UIApplication.shared.applicationState == .active else { throw ConnectFailure.permissionDenied }
                    try reserve(metadata.size, incoming: true, peer: peer)
                    var row = MobileFileReceipt(id: id, peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date())
                    row.state = "awaiting_approval"; try put(row)
                }
            }
            guard var row = receipts.first(where: { $0.id == id }), row.peerID == peer else { throw ConnectFailure.fileTransferInterrupted }
            if operation == "cancel" { end(id, state: "cancelled") }
            else if operation == "chunk" || operation == "complete" {
                guard row.incoming else { throw ConnectFailure.permissionDenied }
                if !FileWire.terminal.contains(row.state) {
                    guard ["accepted", "transferring"].contains(row.state), hashes[id] != nil else { throw ConnectFailure.permissionDenied }
                    if operation == "chunk" {
                        guard request["arguments"]["offset"] == .int(row.received), row.received + Int64(bytes.count) <= row.metadata.size else { end(id, state: "failed"); throw ConnectFailure.fileHashMismatch }
                        let handle = try FileHandle(forWritingTo: staging.path(id, "part")); defer { try? handle.close() }
                        try handle.seekToEnd(); try handle.write(contentsOf: bytes)
                        hashes[id]?.update(data: bytes); row.received += Int64(bytes.count); row.state = "transferring"; row.touched = Date(); try put(row)
                        try background?.progress(row.received, total: row.metadata.size, id: id)
                    } else {
                        guard row.received == row.metadata.size, Data(hashes[id]!.finalize()).hex == row.metadata.sha256 else { end(id, state: "failed"); throw ConnectFailure.fileHashMismatch }
                        let partial = try staging.path(id, "part"), final = try staging.path(id, "bin")
                        let handle = try FileHandle(forWritingTo: partial); try handle.synchronize(); try handle.close()
                        try FileManager.default.linkItem(at: partial, to: final)
                        pendingCompletion[requestID] = id
                        end(id, state: "completed", deferCompletion: true)
                        guard receipts.first(where: { $0.id == id })?.state == "completed" else { pendingCompletion.removeValue(forKey: requestID); throw ConnectFailure.localStorageUnavailable }
                        notice = "Incoming file verified · Ready to Save"
                    }
                }
            }
            guard let current = receipts.first(where: { $0.id == id }) else { throw ConnectFailure.fileTransferInterrupted }
            response = .object(["protocol_version": .string("olive-files/1"), "request_id": .string(requestID), "state": .string("completed"),
                "result": .object(["state": .string(current.state), "received_size": .int(current.received)])])
        } catch {
            response = .object(["protocol_version": .string("olive-files/1"), "request_id": .string(requestID), "state": .string("rejected"),
                "error": .string((error as? ConnectFailure) == .fileHashMismatch ? "content_integrity_failed" : "file_transfer_rejected")])
        }
        return ConnectFrame(kind: 8, payload: response.canonical)
    }
}
