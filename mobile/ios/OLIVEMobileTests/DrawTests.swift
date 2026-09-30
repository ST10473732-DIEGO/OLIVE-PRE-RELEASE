import XCTest
import ImageIO
import SQLite3
import UniformTypeIdentifiers
@testable import OLIVEMobile

// OLIVE Draw on the phone: the native Swift replica, store, codec, sync engine,
// assets, renderer and input model. Synthetic data only.

private func tempDirectory() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("olive-draw-tests-" + UUID().uuidString, isDirectory: true)
    try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

private func sharedFile(_ name: String) throws -> Data {
    let url = try XCTUnwrap(Bundle(for: DrawDocumentTests.self).url(forResource: name, withExtension: nil), "\(name) not bundled")
    return try Data(contentsOf: url)
}

private func stroke(_ points: [Double], color: String = "#000000", width: Double = 4, opacity: Double = 1, pressure: Bool = false) -> DrawOp {
    .stroke(id: DrawText.randomID(), color: DrawColor(hex: color), width: width, opacity: opacity, pressure: pressure, points: points)
}
private func erase(_ points: [Double], width: Double = 20) -> DrawOp { .erase(id: DrawText.randomID(), width: width, points: points) }
private func clearOp() -> DrawOp { .clear(id: DrawText.randomID()) }
private func backgroundOp(_ value: String) -> DrawOp { .background(id: DrawText.randomID(), value: value) }

/// Synthetic PNG (optionally with a transparent top-left quarter).
private func pngData(_ width: Int, _ height: Int, rgba: [Double] = [1, 0, 0, 1], transparentCorner: Bool = false) -> Data {
    let context = DrawRender.makeContext(width: width, height: height)!
    context.setFillColor(CGColor(colorSpace: DrawRender.sRGB, components: rgba.map { CGFloat($0) })!)
    context.fill(CGRect(x: 0, y: 0, width: width, height: height))
    if transparentCorner { context.clear(CGRect(x: 0, y: 0, width: width / 2, height: height / 2)) }
    return try! DrawAssets.encodeImage(context.makeImage()!, png: true, quality: 1)
}

/// Synthetic JPEG (left half red, right half blue) with EXIF orientation 6, a
/// camera make/model, a timestamp and GPS coordinates. Not a real photo.
private func jpegWithExifGPS(width: Int = 64, height: Int = 32, orientation: Int = 6, type: UTType = .jpeg) -> Data {
    let context = DrawRender.makeContext(width: width, height: height, opaque: true)!
    context.setFillColor(CGColor(srgbRed: 0.86, green: 0.08, blue: 0.08, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: width / 2, height: height))
    context.setFillColor(CGColor(srgbRed: 0.08, green: 0.08, blue: 0.86, alpha: 1))
    context.fill(CGRect(x: width / 2, y: 0, width: width - width / 2, height: height))
    let output = NSMutableData()
    let destination = CGImageDestinationCreateWithData(output, type.identifier as CFString, 1, nil)!
    let properties: [CFString: Any] = [
        kCGImagePropertyOrientation: orientation,
        kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFMake: "SyntheticCam", kCGImagePropertyTIFFModel: "Model Fixture",
                                         kCGImagePropertyTIFFDateTime: "2026:09:30 10:00:00"],
        kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:09:30 10:00:00"],
        kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 51.5, kCGImagePropertyGPSLatitudeRef: "N",
                                        kCGImagePropertyGPSLongitude: 0.12, kCGImagePropertyGPSLongitudeRef: "W"],
        kCGImageDestinationLossyCompressionQuality: 0.95,
    ]
    CGImageDestinationAddImage(destination, context.makeImage()!, properties as CFDictionary)
    precondition(CGImageDestinationFinalize(destination))
    return output as Data
}

private func properties(_ data: Data) -> [CFString: Any] {
    let source = CGImageSourceCreateWithData(data as CFData, nil)!
    return CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] ?? [:]
}

private func drawRecord(_ kind: String, drawing: String, device: String, lamport: Int64, id: String = DrawText.randomID(), body: ConnectJSON) -> ConnectJSON {
    .object(["record_id": .string(id), "drawing_id": .string(drawing), "device": .string(device), "lamport": .int(lamport),
             "kind": .string(kind), "at": .string("2026-09-30T10:00:00.000Z"), "body": body])
}

// MARK: - Document model, conformance, shared contract

final class DrawDocumentTests: XCTestCase {
    func testLimitsMirrorTheSharedDesktopSchemaAndProtocolFiles() throws {
        let schema = try ConnectJSON.decode(try sharedFile("drawing_schema.json"), limit: 100_000, allowDecimals: true)
        XCTAssertEqual(schema["schema_version"].integer, Int64(DrawSpec.schemaVersion))
        let limits = try XCTUnwrap(schema["limits"].object)
        XCTAssertEqual(Set(limits.keys), Set(DrawSpec.limitTable.keys))
        for (key, value) in limits { XCTAssertEqual(value.drawNumber, DrawSpec.limitTable[key], key) }
        XCTAssertEqual(schema["operations"]["1"].array?.compactMap(\.string), DrawSpec.operationsBySchema[1])
        XCTAssertEqual(schema["operations"]["2"].array?.compactMap(\.string), DrawSpec.operationsBySchema[2])
        XCTAssertEqual(schema["record_kinds"].array?.compactMap(\.string), DrawSpec.recordKinds)
        XCTAssertEqual(schema["meta_fields"].array?.compactMap(\.string), DrawSpec.metaFields)
        XCTAssertEqual(schema["backgrounds"].array?.compactMap(\.string), DrawSpec.backgrounds)
        XCTAssertEqual(schema["image_types"].array?.compactMap(\.string), DrawSpec.imageTypes)
        let wire = try ConnectJSON.decode(try sharedFile("protocol_v1.json"), limit: 100_000)
        XCTAssertEqual(wire["protocol"].string, DrawProtocol.name)
        XCTAssertEqual(wire["capability"].string, DrawProtocol.capability)
        XCTAssertEqual(wire["frames"]["request"].integer, Int64(DrawProtocol.requestFrame))
        XCTAssertEqual(wire["frames"]["response"].integer, Int64(DrawProtocol.responseFrame))
        XCTAssertEqual(wire["document_schemas"].array?.compactMap(\.integer), DrawProtocol.documentSchemas)
        let wireLimits = try XCTUnwrap(wire["limits"].object)
        XCTAssertEqual(Set(wireLimits.keys), Set(DrawProtocol.limitTable.keys))
        for (key, value) in wireLimits { XCTAssertEqual(value.integer, Int64(DrawProtocol.limitTable[key]!), key) }
        for (operation, fields) in DrawProtocol.operations {
            XCTAssertEqual(wire["operations"][operation]["required"].array?.compactMap(\.string), fields)
        }
        XCTAssertEqual(wire["statuses"].array?.compactMap(\.string), DrawProtocol.statuses)
        XCTAssertEqual(wire["asset_statuses"].array?.compactMap(\.string), DrawProtocol.assetStatuses)
        XCTAssertEqual(wire["errors"].array?.compactMap(\.string), DrawProtocol.errors)
        XCTAssertEqual(try ConnectFrame.limit(15), DrawProtocol.Limit.maxFrameBytes)
        XCTAssertEqual(try ConnectFrame.limit(16), DrawProtocol.Limit.maxFrameBytes)
    }

    /// The shared fixture, through BOTH phone implementations (in-memory replica
    /// and SQLite store), in many random arrival orders, with duplicates.
    func testSharedConformanceFixtureInRandomArrivalOrders() async throws {
        let fixture = try ConnectJSON.decode(try sharedFile("conformance_v1.json"), limit: 2_000_000, allowDecimals: true)
        var generator = SeededGenerator(seed: 7)
        for scenario in try XCTUnwrap(fixture["scenarios"].array) {
            let name = scenario["name"].string ?? ""
            let records = try XCTUnwrap(scenario["records"].array)
            let expect = scenario["expect"]
            let did = records[0]["drawing_id"].string!
            for attempt in 0..<16 {
                let order = records.shuffled(using: &generator)
                // In-memory replica.
                var replica = DrawReplica(drawingID: did)
                for value in order { replica.apply(try DrawRecord.validate(value)) }
                for value in order { XCTAssertEqual(replica.apply(try DrawRecord.validate(value)), DrawReplica.Change(), "\(name) duplicate") }
                XCTAssertEqual(replica.order, expect["order"].array?.compactMap(\.string), "\(name) #\(attempt)")
                let visible = replica.visible()
                XCTAssertEqual(visible.map(\.id), expect["visible"].array?.compactMap(\.string), "\(name) #\(attempt)")
                XCTAssertEqual(replica.title, expect["title"].string)
                XCTAssertEqual(replica.trashed, expect["trashed"].boolean)
                XCTAssertEqual(visible.effectiveBackground(replica.create!.background), expect["background"].string)
                XCTAssertEqual(replica.create?.width, Int(expect["width"].integer!))
                XCTAssertEqual(replica.create?.height, Int(expect["height"].integer!))
                // SQLite store (the phone's durable replica).
                if attempt < 6 {
                    let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
                    let applied = try await engine.insertRecords(order)
                    XCTAssertEqual(applied, Array(repeating: "applied", count: order.count), name)
                    let again = try await engine.insertRecords(order)
                    XCTAssertEqual(again, Array(repeating: "duplicate", count: order.count), name)
                    let stored = try await engine.operationOrder(did)
                    XCTAssertEqual(stored, expect["order"].array?.compactMap(\.string), name)
                    let ops = try await engine.visibleOperations(did)
                    XCTAssertEqual(ops.map(\.id), expect["visible"].array?.compactMap(\.string), name)
                    let summary = try await engine.summary(did)
                    XCTAssertEqual(summary.title, expect["title"].string, name)
                    XCTAssertEqual(summary.trashed, expect["trashed"].boolean, name)
                    XCTAssertEqual(ops.effectiveBackground(summary.background), expect["background"].string, name)
                }
            }
        }
    }

    func testRecordValidationIsStrict() throws {
        let did = UUID().uuidString.lowercased(), device = UUID().uuidString.lowercased()
        let good = drawRecord("op", drawing: did, device: device, lamport: 3, id: "0123456789abcdef0123456789abcdef",
                          body: stroke([1, 2, 3, 4]).with(id: "0123456789abcdef0123456789abcdef").json)
        XCTAssertNoThrow(try DrawRecord.validate(good))
        func mutate(_ change: (inout [String: ConnectJSON]) -> Void) -> ConnectJSON {
            var object = good.object!; change(&object); return .object(object)
        }
        let bad: [ConnectJSON] = [
            mutate { $0["extra"] = .int(1) },
            mutate { $0["record_id"] = .string("XYZ") },
            mutate { $0["device"] = .string("not-a-uuid") },
            mutate { $0["lamport"] = .int(0) },
            mutate { $0["lamport"] = .int((1 << 53) + 1) },
            mutate { $0["lamport"] = .bool(true) },
            mutate { $0["lamport"] = .decimal("2.0") },
            mutate { $0["at"] = .string("2026-09-30 10:00:00") },
            mutate { $0["kind"] = .string("script") },
            mutate { $0["body"] = stroke([1, 2]).json },                                     // body id != record id
            mutate { $0["body"] = .object(["type": .string("stroke")]) },
        ]
        for value in bad { XCTAssertThrowsError(try DrawRecord.validate(value)) }
        // Operation bodies.
        let id = "abcdefabcdefabcdefabcdefabcdefab"
        let badOps: [ConnectJSON] = [
            .object(["type": .string("stroke"), "id": .string(id), "tool": .string("pen"), "color": .string("#FF0000"), "width": .int(4),
                     "opacity": .int(1), "pressure": .bool(false), "points": .array([.int(1), .int(2)])]),       // uppercase colour
            .object(["type": .string("stroke"), "id": .string(id), "tool": .string("pen"), "color": .string("#ff0000"), "width": .int(300),
                     "opacity": .int(1), "pressure": .bool(false), "points": .array([.int(1), .int(2)])]),       // width > 256
            .object(["type": .string("stroke"), "id": .string(id), "tool": .string("pen"), "color": .string("#ff0000"), "width": .int(4),
                     "opacity": .int(1), "pressure": .bool(true), "points": .array([.int(1), .int(2), .decimal("1.5")])]),  // pressure > 1
            .object(["type": .string("stroke"), "id": .string(id), "tool": .string("pen"), "color": .string("#ff0000"), "width": .bool(true),
                     "opacity": .int(1), "pressure": .bool(false), "points": .array([.int(1), .int(2)])]),       // bool as number
            .object(["type": .string("erase"), "id": .string(id), "width": .int(4), "points": .array([.int(1)])]),  // odd points
            .object(["type": .string("image"), "id": .string(id), "asset_id": .string("../etc/passwd"), "x": .int(0), "y": .int(0),
                     "width": .int(1), "height": .int(1), "opacity": .int(1)]),
            .object(["type": .string("background"), "id": .string(id), "value": .string("#000000")]),
            .object(["type": .string("hologram"), "id": .string(id)]),
        ]
        for value in badOps { XCTAssertThrowsError(try DrawOp(json: value)) }
        let tooMany = ConnectJSON.array(Array(repeating: .int(1), count: (DrawSpec.Limit.maxPoints + 1) * 2))
        XCTAssertThrowsError(try DrawOp(json: .object(["type": .string("erase"), "id": .string(id), "width": .int(4), "points": tooMany])))
        // Titles are plain text.
        XCTAssertEqual(DrawText.cleanTitle("  A\u{0007}  b\nc\u{200b}  "), "A b c")
        XCTAssertEqual(DrawText.cleanTitle(String(repeating: "é", count: 300)).count, 200)
        let hostile = drawRecord("meta", drawing: did, device: device, lamport: 2, body: .object(["field": .string("title"), "value": .string("<script>\u{0000}")]))
        XCTAssertThrowsError(try DrawRecord.validate(hostile))
        XCTAssertNoThrow(try DrawRecord.validate(drawRecord("meta", drawing: did, device: device, lamport: 2,
                                                        body: .object(["field": .string("title"), "value": .string("<script>alert(1)</script>")]))))
    }

    func testOperationIDsAreRandom128BitHexAndNumbersRoundTrip() throws {
        let ids = (0..<500).map { _ in DrawText.randomID() }
        XCTAssertEqual(Set(ids).count, 500)
        XCTAssertTrue(ids.allSatisfy(DrawText.isRecordID))
        let op = DrawOp.stroke(id: ids[0], color: DrawColor(hex: "#1e63e9"), width: 12.5, opacity: 0.35, pressure: true,
                               points: [10.25, 20, 0.123, 1e-2, 24575.99, 1])
        let text = String(decoding: op.json.canonical, as: UTF8.self)
        XCTAssertTrue(text.contains("\"points\":[10.25,20,0.123,0.01,24575.99,1]"), text)
        XCTAssertEqual(try DrawOp(json: ConnectJSON.decode(op.json.canonical, limit: 10_000, allowDecimals: true)), op)
        XCTAssertEqual(DrawQuantize.coordinate(10.005), 10.01)
        XCTAssertEqual(DrawQuantize.coordinate(-3.14159), -3.14)
        XCTAssertEqual(DrawQuantize.pressure(1.7), 1)
        XCTAssertEqual(DrawQuantize.pressure(0.12345), 0.123)
    }

    func testPressureWidthRuleMatchesDesktop() {
        XCTAssertEqual(drawPressureWidth(0), 0.2, accuracy: 1e-12)
        XCTAssertEqual(drawPressureWidth(0.5), 0.6, accuracy: 1e-12)
        XCTAssertEqual(drawPressureWidth(1), 1, accuracy: 1e-12)
        XCTAssertEqual(40 * drawPressureWidth(0.25), 16, accuracy: 1e-12)
    }

    func testExportNamesAreSanitized() {
        XCTAssertEqual(DrawText.exportName("../../etc/passwd", ext: "png"), "etc passwd.png")
        XCTAssertEqual(DrawText.exportName("A\nB\u{0000}C:D", ext: "jpg"), "A B C D.jpg")
        XCTAssertEqual(DrawText.exportName("   ", ext: "png"), "Drawing.png")
    }
}

// MARK: - Store, engine, undo, library, corruption

final class DrawStoreTests: XCTestCase {
    func testLocalEditsLamportUndoRedoAndRestartPersistence() async throws {
        let directory = tempDirectory(), device = UUID().uuidString.lowercased()
        var engine: DrawEngine? = DrawEngine(directory: directory, deviceID: device)
        let did = try await engine!.create(title: "Phone", width: 400, height: 300).id
        let a = stroke([1, 1, 50, 50]), b = erase([10, 0, 10, 100]), c = backgroundOp("transparent")
        for op in [a, b, c] { _ = try await engine!.append(did, op) }
        let d = try await engine!.append(did, clearOp())
        XCTAssertEqual(d.record?.lamport, 5)
        XCTAssertEqual(d.undo, 4); XCTAssertEqual(d.redo, 0)
        // Retrying the same op id is recognised (idempotent).
        _ = try await engine!.append(did, a)
        let visible = try await engine!.visibleOperations(did)
        XCTAssertEqual(visible.count, 4)
        let undone = try await engine!.undo(did)
        XCTAssertEqual(undone.record?.body["target"].string, d.record?.recordID)
        XCTAssertEqual(undone.record?.kind, "visibility")
        // Restart: the stacks and the pictures are durable.
        engine = nil
        engine = DrawEngine(directory: directory, deviceID: device)
        let history = try await engine!.history(did)
        XCTAssertEqual(history.undo, 3); XCTAssertEqual(history.redo, 1)
        _ = try await engine!.redo(did)
        let after = try await engine!.visibleOperations(did)
        XCTAssertEqual(after.map(\.id), [a.id, b.id, c.id, d.record!.recordID])
        // A new local edit after Undo clears the Redo stack.
        _ = try await engine!.undo(did)
        let fresh = try await engine!.append(did, stroke([5, 5, 6, 6]))
        XCTAssertEqual(fresh.redo, 0)
    }

    func testRemoteEditsAreNeverUndoneLocallyAndDoNotDestroyRedo() async throws {
        let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
        let did = try await engine.create(title: "Shared", width: 300, height: 300).id
        let desktop = UUID().uuidString.lowercased()
        let red = stroke([10, 50, 290, 50], color: "#e53935")
        _ = try await engine.insertRecords([drawRecord("op", drawing: did, device: desktop, lamport: 2, id: red.id, body: red.json)], source: desktop)
        let blue = try await engine.append(did, stroke([10, 150, 290, 150], color: "#1e63e9"))
        XCTAssertEqual(blue.record?.lamport, 3)                      // max(seen) + 1
        let green = stroke([10, 250, 290, 250], color: "#43a047")
        _ = try await engine.insertRecords([drawRecord("op", drawing: did, device: desktop, lamport: 4, id: green.id, body: green.json)], source: desktop)
        let undo = try await engine.undo(did)
        XCTAssertEqual(undo.record?.body["target"].string, blue.record?.recordID)   // the phone's own blue, not the later green
        var visible = try await engine.visibleOperations(did)
        XCTAssertEqual(visible.map(\.id), [red.id, green.id])
        // A remote edit between Undo and Redo leaves Redo intact.
        let other = stroke([1, 1, 2, 2])
        _ = try await engine.insertRecords([drawRecord("op", drawing: did, device: desktop, lamport: 9, id: other.id, body: other.json)], source: desktop)
        _ = try await engine.redo(did)
        visible = try await engine.visibleOperations(did)
        XCTAssertEqual(visible.map(\.id), [red.id, blue.record!.recordID, green.id, other.id])
        // Nothing of the desktop's is in the phone's stack.
        _ = try await engine.undo(did)
        let empty = try await engine.undo(did)
        XCTAssertNil(empty.record)
        // A visibility record by the phone targeting a desktop op is ignored.
        let me = await engine.deviceID
        let forged = drawRecord("visibility", drawing: did, device: me, lamport: 20,
                            body: .object(["target": .string(red.id), "hidden": .bool(true)]))
        _ = try await engine.insertRecords([forged])
        visible = try await engine.visibleOperations(did)
        XCTAssertTrue(visible.map(\.id).contains(red.id))
    }

    func testLibraryRenameDuplicateTrashRestorePurgeAndTombstone() async throws {
        let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
        let first = try await engine.create(title: "OLIVE Draw Library Test", width: 800, height: 600, background: "transparent")
        let data = pngData(40, 20)
        let info = try await engine.storeAsset(data)
        _ = try await engine.append(first.id, .image(id: DrawText.randomID(), assetID: info.assetID, x: 10, y: 10, width: 40, height: 20, opacity: 1))
        _ = try await engine.append(first.id, stroke([1, 1, 5, 5]))
        _ = try await engine.rename(first.id, title: "  Renamed\n drawing ")
        let renamed = try await engine.summary(first.id)
        XCTAssertEqual(renamed.title, "Renamed drawing")
        XCTAssertEqual(renamed.schemaVersion, 2)                         // an image op makes it schema 2
        let copy = try await engine.duplicate(first.id)
        XCTAssertNotEqual(copy.id, first.id)
        XCTAssertEqual(copy.title, "Renamed drawing (copy)")
        XCTAssertEqual(copy.background, "transparent")
        let copied = try await engine.visibleOperations(copy.id)
        let original = try await engine.visibleOperations(first.id)
        XCTAssertEqual(copied.count, 2)
        XCTAssertEqual(copied.compactMap(\.assetID), original.compactMap(\.assetID))   // same asset, no new bytes
        XCTAssertNotEqual(copied.map(\.id), original.map(\.id))
        let copyHistory = try await engine.history(copy.id)
        XCTAssertEqual(copyHistory.undo, 2)
        // Duplicate titles are allowed.
        _ = try await engine.create(title: "Renamed drawing", width: 16, height: 16)
        // Trash, restore, purge (only from trash), tombstone.
        await XCTAssertThrowsErrorAsync(try await engine.purge(first.id)) { XCTAssertEqual(($0 as? DrawError)?.code, "not_in_trash") }
        _ = try await engine.trash(first.id)
        var trash = try await engine.list(trash: true)
        XCTAssertEqual(trash.map(\.id), [first.id])
        await XCTAssertThrowsErrorAsync(try await engine.append(first.id, stroke([1, 1, 2, 2]))) { XCTAssertEqual(($0 as? DrawError)?.code, "in_trash") }
        _ = try await engine.restore(first.id)
        _ = try await engine.trash(first.id)
        try await engine.purge(first.id)
        trash = try await engine.list(trash: true)
        XCTAssertTrue(trash.isEmpty)
        let purged = try await engine.isPurged(first.id)
        XCTAssertTrue(purged)
        // A stale record for the purged drawing is dropped.
        let stale = stroke([1, 1, 2, 2])
        let statuses = try await engine.insertRecords([drawRecord("op", drawing: first.id, device: UUID().uuidString.lowercased(), lamport: 99, id: stale.id, body: stale.json)])
        XCTAssertEqual(statuses, ["purged"])
        // Assets are retained after purge (another drawing still uses them).
        let kept = try await engine.assetInfo(info.assetID)
        XCTAssertNotNil(kept)
    }

    func testLimitsAreRefusedNeverTruncated() async throws {
        let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
        await XCTAssertThrowsErrorAsync(try await engine.create(width: 8193, height: 16))
        await XCTAssertThrowsErrorAsync(try await engine.create(width: 15, height: 100))
        await XCTAssertThrowsErrorAsync(try await engine.create(width: 8192, height: 8192))      // > 33.5 M pixels
        let did = try await engine.create(width: 100, height: 100).id
        await XCTAssertThrowsErrorAsync(try await engine.append(did, .stroke(id: DrawText.randomID(), color: DrawColor(hex: "#000000"),
            width: 300, opacity: 1, pressure: false, points: [1, 1])))
        var capture = DrawStrokeCapture()
        XCTAssertTrue(capture.begin(.init(x: 0, y: 0, pressure: 0), tool: .pen, source: .finger, minDistance: 0))
        _ = capture.move((1...10_050).map { .init(x: Double($0), y: 0, pressure: 0) })
        XCTAssertTrue(capture.limited)
        XCTAssertEqual(capture.end()?.points.count, DrawSpec.Limit.maxPoints * 2)
    }

    func testDataProtectionAndBackupExclusionOnTheDeviceStore() async throws {
        let directory = tempDirectory().appendingPathComponent("Draw", isDirectory: true)
        let engine = DrawEngine(directory: directory, deviceID: UUID().uuidString.lowercased())
        _ = try await engine.create(title: "Protection", width: 100, height: 100)
        let url = directory.appendingPathComponent(DrawStore.fileName)
        #if targetEnvironment(simulator)
        throw XCTSkip("File protection classes are only enforced on a physical device")
        #else
        for path in [url.path, url.path + "-wal", url.path + "-shm"] where FileManager.default.fileExists(atPath: path) {
            let protection = try FileManager.default.attributesOfItem(atPath: path)[.protectionKey] as? FileProtectionType
            XCTAssertEqual(protection, .completeUntilFirstUserAuthentication, path.components(separatedBy: "/").last ?? "")
        }
        let folder = try FileManager.default.attributesOfItem(atPath: directory.path)[.protectionKey] as? FileProtectionType
        XCTAssertEqual(folder, .completeUntilFirstUserAuthentication)
        XCTAssertEqual(try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        #endif
    }

    func testUnreadableAndNewerStoresAreNeverModified() async throws {
        let garbage = tempDirectory()
        let url = garbage.appendingPathComponent(DrawStore.fileName)
        let junk = Data("this is not an OLIVE drawing database".utf8) + Data(repeating: 7, count: 4000)
        try junk.write(to: url)
        let broken = DrawEngine(directory: garbage, deviceID: UUID().uuidString.lowercased())
        let available = await broken.available
        XCTAssertFalse(available)
        await XCTAssertThrowsErrorAsync(try await broken.list(trash: false))
        XCTAssertEqual(try Data(contentsOf: url), junk)                             // retained, not replaced by an empty store
        // Newer store schema: refused, untouched.
        let newer = tempDirectory()
        do { _ = try DrawStore(directory: newer) }   // closed deterministically at the end of this scope
        let path = newer.appendingPathComponent(DrawStore.fileName).path
        var db: OpaquePointer?
        XCTAssertEqual(sqlite3_open(path, &db), SQLITE_OK)
        sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE); PRAGMA user_version=3", nil, nil, nil)
        sqlite3_close(db)
        let before = try Data(contentsOf: URL(fileURLWithPath: path))
        let refused = DrawEngine(directory: newer, deviceID: UUID().uuidString.lowercased())
        let newerAvailable = await refused.available
        XCTAssertFalse(newerAvailable)
        XCTAssertEqual(refused.unavailable, .newer)
        XCTAssertEqual(try Data(contentsOf: URL(fileURLWithPath: path)), before)
    }

    func testCorruptedRecordMakesTheDrawingUnreadableAndIsNeverSent() async throws {
        let directory = tempDirectory()
        let phone = DrawEngine(directory: directory, deviceID: UUID().uuidString.lowercased())
        let did = try await phone.create(title: "Corrupt", width: 100, height: 100).id
        let op = stroke([1, 1, 2, 2])
        _ = try await phone.append(did, op)
        var db: OpaquePointer?
        XCTAssertEqual(sqlite3_open(directory.appendingPathComponent(DrawStore.fileName).path, &db), SQLITE_OK)
        sqlite3_exec(db, "UPDATE draw_records SET body='{\"broken' WHERE record_id='\(op.id)'", nil, nil, nil)
        sqlite3_close(db)
        await XCTAssertThrowsErrorAsync(try await phone.since(did)) { XCTAssertEqual(($0 as? DrawError)?.code, "drawing_corrupted") }
        let net = SimNet()
        let desktop = await net.node(allowAll: true)
        let phoneNode = await net.add(engine: phone, allowAll: true)
        _ = try await net.sync(from: phoneNode, to: desktop)
        let received = try await desktop.engine.visibleOperations(did)
        XCTAssertTrue(received.isEmpty)                                            // the create synced; the corrupt op did not
        let kept = try await phone.summary(did)                                  // data kept for recovery
        XCTAssertEqual(kept.id, did)
    }
}

// MARK: - Assets

final class DrawAssetTests: XCTestCase {
    func testHeaderValidationAndContentAddressing() throws {
        let data = pngData(40, 20)
        let info = try DrawAssets.validate(data)
        XCTAssertEqual(info.assetID, DrawText.sha256(data))
        XCTAssertEqual([info.mime, "\(info.width)x\(info.height)"], ["image/png", "40x20"])
        XCTAssertThrowsError(try DrawAssets.validate(data, expectedID: String(repeating: "0", count: 64))) {
            XCTAssertEqual(($0 as? DrawAssets.Failure)?.code, "checksum_mismatch")
        }
        XCTAssertThrowsError(try DrawAssets.validate(Data("GIF89a....".utf8))) { XCTAssertEqual(($0 as? DrawAssets.Failure)?.code, "unsupported_image") }
        XCTAssertThrowsError(try DrawAssets.validate(Data(data.prefix(data.count - 16)))) { XCTAssertEqual(($0 as? DrawAssets.Failure)?.code, "invalid_image") }
        var huge = data
        huge.replaceSubrange(16..<20, with: [0, 0, 0x27, 0x10])                    // width 10000 in the header
        XCTAssertThrowsError(try DrawAssets.validate(huge)) { XCTAssertEqual(($0 as? DrawAssets.Failure)?.code, "image_too_large") }
        XCTAssertThrowsError(try DrawAssets.canonicalize(Data("<svg/>".utf8), canvasWidth: 100, canvasHeight: 100))
        var bomb = pngData(10, 10)
        bomb.replaceSubrange(16..<24, with: [0, 0, 0x40, 0, 0, 0, 0x40, 0])       // 16384 × 16384 declared
        XCTAssertThrowsError(try DrawAssets.canonicalize(bomb, canvasWidth: 100, canvasHeight: 100)) {
            XCTAssertEqual(($0 as? DrawAssets.Failure)?.code, "image_too_large")
        }
    }

    func testImportStripsExifGPSAppliesOrientationAndConvertsToSRGB() throws {
        let source = jpegWithExifGPS()
        let sourceProperties = properties(source)
        XCTAssertNotNil(sourceProperties[kCGImagePropertyGPSDictionary])           // the fixture really has GPS
        let imported = try DrawAssets.canonicalize(source, canvasWidth: 400, canvasHeight: 300)
        XCTAssertEqual([imported.info.mime, "\(imported.width)x\(imported.height)"], ["image/jpeg", "32x64"])   // rotated 90°
        XCTAssertEqual([imported.x, imported.y], [184, 118])
        let out = properties(imported.data)
        XCTAssertNil(out[kCGImagePropertyGPSDictionary])
        XCTAssertNil((out[kCGImagePropertyTIFFDictionary] as? [CFString: Any])?[kCGImagePropertyTIFFMake])
        XCTAssertNil((out[kCGImagePropertyTIFFDictionary] as? [CFString: Any])?[kCGImagePropertyTIFFModel])
        XCTAssertNil((out[kCGImagePropertyExifDictionary] as? [CFString: Any])?[kCGImagePropertyExifDateTimeOriginal])
        XCTAssertEqual(out[kCGImagePropertyOrientation] as? Int ?? 1, 1)
        for marker in ["SyntheticCam", "Model Fixture", "2026:09:30", "Exif", "Photoshop"] {
            XCTAssertNil(imported.data.range(of: Data(marker.utf8)), marker)
        }
        XCTAssertNil(out[kCGImagePropertyExifDictionary])                             // no EXIF block at all
        let png = try DrawAssets.canonicalize(pngData(30, 20), canvasWidth: 100, canvasHeight: 100)
        for chunk in ["eXIf", "tEXt", "iTXt", "zTXt", "tIME"] { XCTAssertNil(png.data.range(of: Data(chunk.utf8)), chunk) }
        let image = try XCTUnwrap(DrawAssets.decode(imported.data))
        let top = DrawRender.pixel(image, x: 16, y: 8), bottom = DrawRender.pixel(image, x: 16, y: 56)
        XCTAssertGreaterThan(top[0], 180); XCTAssertLessThan(top[2], 80)          // red half on top after rotation
        XCTAssertGreaterThan(bottom[2], 180); XCTAssertLessThan(bottom[0], 80)
        XCTAssertEqual(image.colorSpace?.name, CGColorSpace.sRGB)
    }

    func testHEICPhotoBecomesCanonicalJPEGWithoutMetadata() throws {
        let source = jpegWithExifGPS(width: 80, height: 40, orientation: 1, type: .heic)
        guard properties(source)[kCGImagePropertyPixelWidth] != nil else { throw XCTSkip("HEIC encoding unavailable here") }
        let imported = try DrawAssets.canonicalize(source, canvasWidth: 200, canvasHeight: 200)
        XCTAssertEqual(imported.info.mime, "image/jpeg")
        XCTAssertNil(properties(imported.data)[kCGImagePropertyGPSDictionary])
    }

    func testPNGTransparencyPlacementAndNeverUpscaling() throws {
        let big = pngData(1000, 500, rgba: [0, 0.78, 0, 1], transparentCorner: true)
        let imported = try DrawAssets.canonicalize(big, canvasWidth: 400, canvasHeight: 300)
        XCTAssertEqual([imported.width, imported.height], [360, 180])
        XCTAssertEqual([imported.x, imported.y], [20, 60])
        XCTAssertEqual(imported.info.mime, "image/png")
        let image = try XCTUnwrap(DrawAssets.decode(imported.data))
        XCTAssertEqual(DrawRender.pixel(image, x: 10, y: 10)[3], 0)
        XCTAssertEqual(DrawRender.pixel(image, x: 300, y: 150), [0, 199, 0, 255])
        let small = try DrawAssets.canonicalize(pngData(20, 10), canvasWidth: 400, canvasHeight: 300)
        XCTAssertEqual([small.width, small.height], [20, 10])
        XCTAssertEqual([small.x, small.y], [190, 145])
        XCTAssertEqual(DrawAssets.placement(imageWidth: 3000, imageHeight: 1000, canvasWidth: 1920, canvasHeight: 1080).width, 1728)
        // Identical bytes are stored once; importing the same PNG twice gives the same id.
        let again = try DrawAssets.canonicalize(big, canvasWidth: 400, canvasHeight: 300)
        XCTAssertEqual(again.info.assetID, imported.info.assetID)
    }

    func testImportedAssetSurvivesSourceRemovalAndRestart() async throws {
        let directory = tempDirectory()
        let file = tempDirectory().appendingPathComponent("synthetic.png")
        try pngData(64, 64, rgba: [0.2, 0.4, 0.8, 1]).write(to: file)
        let engine = DrawEngine(directory: directory, deviceID: UUID().uuidString.lowercased())
        let did = try await engine.create(title: "OLIVE Draw Image Test", width: 200, height: 200).id
        let imported = try DrawAssets.canonicalize(try Data(contentsOf: file), canvasWidth: 200, canvasHeight: 200)
        _ = try await engine.addImage(did, imported)
        try FileManager.default.removeItem(at: file)
        let reopened = DrawEngine(directory: directory, deviceID: UUID().uuidString.lowercased())
        let stored = try await reopened.assetData(imported.info.assetID)
        XCTAssertEqual(stored, imported.data)
        let ops = try await reopened.visibleOperations(did)
        XCTAssertEqual(ops.first?.assetID, imported.info.assetID)
    }

    func testLargeSyntheticImageImportPersistRenderExport() async throws {
        let context = DrawRender.makeContext(width: 4000, height: 3000, opaque: true)!
        for i in 0..<20 {
            context.setFillColor(CGColor(srgbRed: Double(i) / 20, green: 0.5, blue: 1 - Double(i) / 20, alpha: 1))
            context.fill(CGRect(x: i * 200, y: 0, width: 200, height: 3000))
        }
        let source = try DrawAssets.encodeImage(context.makeImage()!, png: false, quality: 0.9)
        let started = Date()
        let imported = try DrawAssets.canonicalize(source, canvasWidth: 1920, canvasHeight: 1080)
        let importSeconds = Date().timeIntervalSince(started)
        XCTAssertEqual([imported.width, imported.height], [1296, 972])
        let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
        let did = try await engine.create(title: "OLIVE Draw Large Image", width: 1920, height: 1080).id
        _ = try await engine.addImage(did, imported)
        _ = try await engine.append(did, stroke([0, 540, 1920, 540], color: "#e53935", width: 40))
        let ops = try await engine.visibleOperations(did)
        let storedBytes = try await engine.assetData(imported.info.assetID)
        let decoded = try XCTUnwrap(DrawAssets.decode(try XCTUnwrap(storedBytes)))
        let renderStart = Date()
        let flat = try XCTUnwrap(DrawRender.rasterize(ops, width: 1920, height: 1080, background: "#ffffff", jpeg: false, images: { _ in decoded }))
        let png = try XCTUnwrap(DrawRender.encode(flat, jpeg: false))
        let jpeg = try XCTUnwrap(DrawRender.encode(try XCTUnwrap(DrawRender.rasterize(ops, width: 1920, height: 1080, background: "#ffffff", jpeg: true,
                                                                                         images: { _ in decoded })), jpeg: true))
        let exportSeconds = Date().timeIntervalSince(renderStart)
        XCTAssertEqual([flat.width, flat.height], [1920, 1080])
        XCTAssertEqual(DrawRender.pixel(flat, x: 960, y: 540), [229, 57, 53, 255])
        print("[draw-perf] 4000×3000 JPEG import \(Int(importSeconds * 1000)) ms → \(imported.data.count) bytes; flatten+PNG+JPEG export \(Int(exportSeconds * 1000)) ms (\(png.count)/\(jpeg.count) bytes)")
    }
}

// MARK: - Rendering

final class DrawRenderTests: XCTestCase {
    private func render(_ ops: [DrawOp], width: Int = 200, height: Int = 100, background: String = "#ffffff", jpeg: Bool = false,
                        images: [String: CGImage] = [:]) -> CGImage {
        DrawRender.rasterize(ops, width: width, height: height, background: ops.effectiveBackground(background), jpeg: jpeg, images: { images[$0] })!
    }

    func testStrokeEraserClearBackgroundImageAndTransparencyPixels() throws {
        let image = try XCTUnwrap(DrawAssets.decode(pngData(20, 20, rgba: [0, 0.5, 1, 1])))
        let assetID = String(repeating: "a", count: 64)
        let ops: [DrawOp] = [
            stroke([10, 50, 190, 50], color: "#e53935", width: 20),
            erase([100, 0, 100, 100], width: 20),
            .image(id: DrawText.randomID(), assetID: assetID, x: 150, y: 70, width: 20, height: 20, opacity: 1),
            stroke([20, 10, 60, 10], color: "#1e63e9", width: 6, opacity: 0.5),
        ]
        let white = render(ops, images: [assetID: image])
        XCTAssertEqual(DrawRender.pixel(white, x: 50, y: 50), [229, 57, 53, 255])     // stroke
        XCTAssertEqual(DrawRender.pixel(white, x: 100, y: 50), [255, 255, 255, 255])  // eraser cut shows the background
        XCTAssertEqual(DrawRender.pixel(white, x: 5, y: 90), [255, 255, 255, 255])    // background
        XCTAssertEqual(DrawRender.pixel(white, x: 160, y: 80), [0, 128, 255, 255])    // image colour, in operation order
        let half = DrawRender.pixel(white, x: 40, y: 10)                               // 50 % blue over white
        XCTAssertEqual(half[0], 143, accuracy: 2); XCTAssertEqual(half[1], 177, accuracy: 2); XCTAssertEqual(half[3], 255)
        let transparent = render(ops + [backgroundOp("transparent")], images: [assetID: image])
        XCTAssertEqual(DrawRender.pixel(transparent, x: 5, y: 90)[3], 0)              // transparent stays transparent (no checkerboard)
        XCTAssertEqual(DrawRender.pixel(transparent, x: 100, y: 50)[3], 0)
        let jpeg = render(ops + [backgroundOp("transparent")], jpeg: true, images: [assetID: image])
        XCTAssertEqual(DrawRender.pixel(jpeg, x: 5, y: 90), [255, 255, 255, 255])      // JPEG: white matte, never black
        // Clear hides earlier ink (and images); a stroke after it survives.
        let cleared = render(ops + [clearOp(), stroke([0, 90, 200, 90], color: "#000000", width: 6)], images: [assetID: image])
        XCTAssertEqual(DrawRender.pixel(cleared, x: 50, y: 50), [255, 255, 255, 255])
        XCTAssertEqual(DrawRender.pixel(cleared, x: 160, y: 80), [255, 255, 255, 255])
        XCTAssertEqual(DrawRender.pixel(cleared, x: 50, y: 90), [0, 0, 0, 255])
        // A later stroke covers the image; a later eraser erases image pixels too.
        let covered = render(ops + [stroke([150, 80, 170, 80], color: "#000000", width: 4), erase([150, 88, 170, 88], width: 4)], images: [assetID: image])
        XCTAssertEqual(DrawRender.pixel(covered, x: 160, y: 80), [0, 0, 0, 255])
        XCTAssertEqual(DrawRender.pixel(covered, x: 160, y: 88), [255, 255, 255, 255])
        // A missing image draws nothing (the placeholder is view-only).
        let missing = render(ops)
        XCTAssertEqual(DrawRender.pixel(missing, x: 160, y: 80), [255, 255, 255, 255])
    }

    func testTranslucentOverlapNeverDarkensAndPressureWidthRule() {
        let loop = stroke([20, 50, 180, 50, 180, 52, 20, 52], color: "#000000", width: 20, opacity: 0.5)
        let image = render([loop])
        let overlap = DrawRender.pixel(image, x: 100, y: 51), single = DrawRender.pixel(image, x: 100, y: 43)
        XCTAssertEqual(overlap[0], single[0], accuracy: 2)                           // composited once
        // Pressure: selected width 40 × (0.2 + 0.8 × p). Measure the drawn width at a steady pressure.
        func measured(_ pressure: Double) -> Int {
            let op = DrawOp.stroke(id: DrawText.randomID(), color: DrawColor(hex: "#000000"), width: 40, opacity: 1, pressure: true,
                                   points: [20, 50, pressure, 100, 50, pressure, 180, 50, pressure])
            let picture = render([op])
            return (0..<100).filter { DrawRender.pixel(picture, x: 100, y: $0)[0] < 128 }.count
        }
        XCTAssertEqual(Double(measured(1)), 40, accuracy: 1.5)
        XCTAssertEqual(Double(measured(0.5)), 24, accuracy: 1.5)
        XCTAssertEqual(Double(measured(0)), 8, accuracy: 1.5)
        // Width is in document pixels: a 40 px stroke is 40 px in an export regardless of screen scale.
        let plain = render([stroke([20, 50, 180, 50], width: 40)])
        XCTAssertEqual((0..<100).filter { DrawRender.pixel(plain, x: 100, y: $0)[0] < 128 }.count, 40, accuracy: 1)
    }

    func testSmoothedPathPassesThroughEndpoints() {
        let path = DrawRender.path([0, 0, 50, 100, 100, 0], stride: 2)
        var points: [CGPoint] = []
        path.applyWithBlock { element in
            let e = element.pointee
            switch e.type {
            case .moveToPoint, .addLineToPoint: points.append(e.points[0])
            case .addQuadCurveToPoint: points.append(e.points[1])
            default: break
            }
        }
        XCTAssertEqual(points.first, CGPoint(x: 0, y: 0))
        XCTAssertEqual(points.last, CGPoint(x: 100, y: 0))
        XCTAssertTrue(points.contains(CGPoint(x: 75, y: 50)), "\(points)")           // midpoint of 2nd→3rd point
        XCTAssertTrue(points.allSatisfy { $0.y >= -1e-9 && $0.y <= 100 + 1e-9 })      // inside the control polygon
    }
}

// MARK: - Input and viewport

final class DrawInputTests: XCTestCase {
    func testFingerHasNoPressureAndPencilPressureOnlyWhenItVaries() {
        var finger = DrawStrokeCapture()
        XCTAssertTrue(finger.begin(.init(x: 1.234, y: 5.678, pressure: 0.9), tool: .pen, source: .finger, minDistance: 0.35))
        XCTAssertFalse(finger.begin(.init(x: 0, y: 0, pressure: 0), tool: .pen, source: .finger, minDistance: 0))   // second finger
        _ = finger.move([.init(x: 10, y: 10, pressure: 0.2), .init(x: 10.1, y: 10.1, pressure: 0.2), .init(x: 20, y: 20, pressure: 0.3)])
        let captured = finger.end(.init(x: 30, y: 30, pressure: 1))!
        XCTAssertFalse(captured.pressure)
        XCTAssertEqual(captured.points, [1.23, 5.68, 10, 10, 20, 20, 30, 30])
        var constant = DrawStrokeCapture()
        _ = constant.begin(.init(x: 0, y: 0, pressure: 0.5), tool: .pen, source: .pencil, minDistance: 0)
        _ = constant.move([.init(x: 5, y: 5, pressure: 0.5)])
        XCTAssertFalse(constant.end()!.pressure)                                         // never fakes pressure
        var pencil = DrawStrokeCapture()
        _ = pencil.begin(.init(x: 0, y: 0, pressure: 0.2), tool: .pen, source: .pencil, minDistance: 0)
        _ = pencil.move([.init(x: 5, y: 5, pressure: 0.8)])
        let pressured = pencil.end()!
        XCTAssertTrue(pressured.pressure)
        XCTAssertEqual(pressured.points, [0, 0, 0.2, 5, 5, 0.8])
        var eraser = DrawStrokeCapture()
        _ = eraser.begin(.init(x: 0, y: 0, pressure: 0.2), tool: .erase, source: .pencil, minDistance: 0)
        _ = eraser.move([.init(x: 5, y: 5, pressure: 0.8)])
        XCTAssertFalse(eraser.end()!.pressure)                                           // erase ops never carry pressure
        var cancelled = DrawStrokeCapture()
        _ = cancelled.begin(.init(x: 0, y: 0, pressure: 0), tool: .pen, source: .finger, minDistance: 0)
        XCTAssertTrue(cancelled.cancel())
        XCTAssertNil(cancelled.end())
    }

    func testViewportZoomPanFitRotationNeverChangeDocumentCoordinates() {
        let document = CGSize(width: 1920, height: 1080), screen = CGSize(width: 390, height: 600)
        let fit = DrawViewport.fit(document: document, viewport: screen)
        XCTAssertEqual(fit.zoom, (390 - 32) / 1920, accuracy: 1e-9)
        XCTAssertEqual(fit.toView(CGPoint(x: 960, y: 540)).x, 195, accuracy: 1e-9)       // centred
        let point = CGPoint(x: 123.45, y: 678.9)
        let anchor = fit.toView(point)
        let zoomed = fit.zoomed(to: 4, around: anchor)
        XCTAssertEqual(zoomed.toDocument(anchor).x, point.x, accuracy: 1e-9)             // zoom around the focal point
        XCTAssertEqual(zoomed.toDocument(anchor).y, point.y, accuracy: 1e-9)
        XCTAssertEqual(fit.zoomed(to: 100, around: .zero).zoom, 16)                      // 1600 %
        XCTAssertEqual(fit.zoomed(to: 0.001, around: .zero).zoom, 0.1)                   // 10 %
        let panned = zoomed.panned(by: CGPoint(x: 1e6, y: -1e6)).clamped(document: document, viewport: screen)
        XCTAssertGreaterThan(panned.toView(CGPoint(x: 1920, y: 0)).x, 0)                // page stays reachable
        let rotated = fit.resized(from: screen, to: CGSize(width: 600, height: 390))
        XCTAssertEqual(rotated.zoom, fit.zoom)
        XCTAssertEqual(rotated.toDocument(CGPoint(x: 300, y: 195)).x, fit.toDocument(CGPoint(x: 195, y: 300)).x, accuracy: 1e-9)
        XCTAssertEqual(DrawBrush.size(slider: DrawBrush.slider(size: 40)), 40)
        XCTAssertEqual(DrawBrush.size(0.7), 0.5)
        XCTAssertEqual(DrawBrush.hex(red: 0.898, green: 0.2235, blue: 0.2078), "#e53935")
    }
}

// MARK: - Sync (two and three Swift replicas over olive-draw/1 bytes)

/// A deterministic in-memory Connect: carries real olive-draw/1 bytes between
/// engines through DrawWire (the same code the app's frames 15/16 use).
actor SimNet {
    struct Node: Sendable { let id: String; let engine: DrawEngine; let directory: URL }
    private var nodes: [String: Node] = [:]
    private var allowed: [String: Set<String>] = [:]
    private var offline = Set<String>()
    var dropResponses = 0
    var duplicate = 0
    var blockAssets = false
    var killAfterChunks: Int?
    private(set) var sent: [(String, Int)] = []

    func node(allowAll: Bool = true) -> Node {
        let directory = tempDirectory()
        let node = Node(id: UUID().uuidString.lowercased(), engine: DrawEngine(directory: directory, deviceID: UUID().uuidString.lowercased()), directory: directory)
        return register(node, allowAll: allowAll)
    }
    func add(engine: DrawEngine, allowAll: Bool) async -> Node {
        let node = Node(id: await engine.deviceID, engine: engine, directory: tempDirectory())
        return register(node, allowAll: allowAll)
    }
    private func register(_ fresh: Node, allowAll: Bool) -> Node {
        // The node's Connect id is its engine's device id.
        let node = fresh
        nodes[node.id] = node
        if allowAll { for other in nodes.keys where other != node.id { allowed[node.id, default: []].insert(other); allowed[other, default: []].insert(node.id) } }
        return node
    }
    func restart(_ node: Node) async -> Node {
        let id = await node.engine.deviceID
        let fresh = Node(id: node.id, engine: DrawEngine(directory: node.directory, deviceID: id), directory: node.directory)
        nodes[node.id] = fresh
        return fresh
    }
    func current(_ node: Node) -> Node { nodes[node.id] ?? node }
    func setAllowed(_ receiver: Node, _ sender: Node, _ value: Bool) {
        if value { allowed[receiver.id, default: []].insert(sender.id) } else { allowed[receiver.id]?.remove(sender.id) }
    }
    func disconnect(_ a: Node, _ b: Node) { offline.insert([a.id, b.id].sorted().joined()) }
    func reconnect(_ a: Node, _ b: Node) { offline.remove([a.id, b.id].sorted().joined()) }
    func setDrop(_ n: Int) { dropResponses = n }
    func setDuplicate(_ n: Int) { duplicate = n }
    func setBlockAssets(_ v: Bool) { blockAssets = v }
    func setKillAfter(_ n: Int?) { killAfterChunks = n }
    func sentCount(_ operation: String) -> Int { sent.filter { $0.0 == operation }.count }

    struct Offline: Error {}

    func deliver(from a: String, to b: String, raw: Data) async throws -> Data {
        guard !offline.contains([a, b].sorted().joined()), let receiver = nodes[b] else { throw Offline() }
        let operation = (try? ConnectJSON.decode(raw, limit: 600_000, allowDecimals: true))?["operation"].string ?? ""
        sent.append((operation, raw.count))
        if operation == "asset" && blockAssets { throw Offline() }
        if operation == "asset", let remaining = killAfterChunks {
            if remaining == 0 {
                killAfterChunks = nil
                _ = await restart(receiver)                       // receiver process dies: staged chunks are gone
                throw Offline()
            }
            killAfterChunks = remaining - 1
        }
        let permitted = allowed[b]?.contains(a) == true
        var response = await DrawWire.receive(engine: nodes[b]!.engine, raw: raw, peer: a, local: b, permitted: permitted, now: DrawWire.now())
        if duplicate > 0 { duplicate -= 1; response = await DrawWire.receive(engine: nodes[b]!.engine, raw: raw, peer: a, local: b, permitted: permitted, now: DrawWire.now()) }
        if dropResponses > 0 { dropResponses -= 1; throw Offline() }
        return response
    }

    nonisolated func sync(from a: Node, to b: Node, hello: Bool = true) async throws -> String {
        let engine = await current(a).engine
        let send = DrawWire.sender(local: a.id, peer: b.id, clock: { DrawWire.now() }) { [self] _, raw in
            try await self.deliver(from: a.id, to: b.id, raw: raw)
        }
        return try await engine.pump(peer: b.id, hello: hello, send: send)
    }

    nonisolated func settle(_ list: [Node]) async {
        for _ in 0..<10 {
            var busy = false
            for a in list {
                for b in list where a.id != b.id {
                    let engine = await current(a).engine
                    let receiver = await current(b).engine
                    let before = ((try? await engine.pending(b.id)) ?? 0, ((try? await receiver.wants()) ?? []).count)
                    guard before.0 > 0 || before.1 > 0 else { continue }
                    _ = try? await sync(from: a, to: b)
                    let after = ((try? await engine.pending(b.id)) ?? 0, ((try? await receiver.wants()) ?? []).count)
                    if after != before { busy = true }
                }
            }
            if !busy { return }
        }
    }
}

/// Deterministic generator for seeded random histories.
struct SeededGenerator: RandomNumberGenerator {
    private var state: UInt64
    init(seed: UInt64) { state = seed &+ 0x9E3779B97F4A7C15 }
    mutating func next() -> UInt64 {
        state &+= 0x9E3779B97F4A7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
}

final class DrawSyncEngineTests: XCTestCase {
    private func state(_ node: SimNet.Node, _ did: String) async throws -> [String] {
        let summary = try await node.engine.summary(did)
        let ops = try await node.engine.visibleOperations(did)
        return [summary.title, "\(summary.trashed)", ops.effectiveBackground(summary.background)] + ops.map(\.id)
    }

    func testPhoneAndDesktopReplicasConvergeWithUndoIsolationOfflineAndFaults() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        let did = try await desktop.engine.create(title: "OLIVE Draw Sync Test", width: 300, height: 300).id
        let red = try await desktop.engine.append(did, stroke([10, 50, 290, 50], color: "#e53935"))
        _ = try await net.sync(from: desktop, to: phone)
        let blue = try await phone.engine.append(did, stroke([10, 150, 290, 150], color: "#1e63e9"))
        _ = try await net.sync(from: phone, to: desktop)
        let green = try await desktop.engine.append(did, stroke([10, 250, 290, 250], color: "#43a047"))
        _ = try await net.sync(from: desktop, to: phone)
        _ = try await phone.engine.undo(did)
        await net.settle([desktop, phone])
        var a = try await state(desktop, did), b = try await state(phone, did)
        XCTAssertEqual(a, b)
        XCTAssertEqual(Array(a.dropFirst(3)), [red.record!.recordID, green.record!.recordID])
        _ = try await phone.engine.redo(did)
        _ = try await desktop.engine.undo(did)
        await net.settle([desktop, phone])
        a = try await state(desktop, did); b = try await state(phone, did)
        XCTAssertEqual(a, b)
        XCTAssertEqual(Array(a.dropFirst(3)), [red.record!.recordID, blue.record!.recordID])
        // Offline edits on both, duplicate delivery, a lost answer, then reconnect.
        await net.disconnect(desktop, phone)
        let purple = try await phone.engine.append(did, stroke([0, 0, 300, 300], color: "#8e24aa"))
        let black = try await desktop.engine.append(did, stroke([300, 0, 0, 300]))
        await XCTAssertThrowsErrorAsync(try await net.sync(from: phone, to: desktop))
        let waiting = try await phone.engine.pending(desktop.id)
        XCTAssertEqual(waiting, 1)                                  // purple (records from the desktop are never echoed back)
        await net.reconnect(desktop, phone)
        await net.setDuplicate(1); await net.setDrop(1)
        _ = try? await net.sync(from: phone, to: desktop)
        await net.settle([desktop, phone])
        a = try await state(desktop, did); b = try await state(phone, did)
        XCTAssertEqual(a, b)
        XCTAssertTrue(a.contains(purple.record!.recordID) && a.contains(black.record!.recordID))
        let pendingAfter = try await phone.engine.pending(desktop.id)
        XCTAssertEqual(pendingAfter, 0)
    }

    func testThreeReplicasSeededRandomHistoriesConvergeInStateAndPixels() async throws {
        for seed in 0..<3 {
            var rng = SeededGenerator(seed: UInt64(seed))
            let net = SimNet()
            let nodes = [await net.node(), await net.node(), await net.node()]
            let did = try await nodes[0].engine.create(title: "Random \(seed)", width: 160, height: 120).id
            await net.settle(nodes)
            for _ in 0..<40 {
                let node = nodes[Int.random(in: 0..<3, using: &rng)]
                if Int.random(in: 0..<4, using: &rng) == 0 {
                    let x = nodes[Int.random(in: 0..<3, using: &rng)], y = nodes[Int.random(in: 0..<3, using: &rng)]
                    if x.id != y.id { if Bool.random(using: &rng) { await net.disconnect(x, y) } else { await net.reconnect(x, y) } }
                }
                let points = (0..<6).map { _ in Double(Int.random(in: 0...16000, using: &rng)) / 100 }
                switch Int.random(in: 0..<9, using: &rng) {
                case 0, 1: _ = try? await node.engine.append(did, stroke(points, color: ["#e53935", "#1e63e9", "#000000"].randomElement(using: &rng)!,
                                                                         width: [2, 8, 20].randomElement(using: &rng)!, opacity: [1, 0.5].randomElement(using: &rng)!))
                case 2: _ = try? await node.engine.append(did, erase(points, width: 12))
                case 3: _ = try? await node.engine.append(did, clearOp())
                case 4: _ = try? await node.engine.append(did, backgroundOp(Bool.random(using: &rng) ? "transparent" : "#ffffff"))
                case 5: _ = try? await node.engine.undo(did)
                case 6: _ = try? await node.engine.redo(did)
                case 7: _ = try? await node.engine.rename(did, title: ["Alpha", "Beta", "Gamma"].randomElement(using: &rng)!)
                default:
                    let trashed = (try? await node.engine.summary(did))?.trashed == true
                    _ = trashed ? try? await node.engine.restore(did) : try? await node.engine.trash(did)
                }
                if Int.random(in: 0..<3, using: &rng) == 0 {
                    let x = nodes[Int.random(in: 0..<3, using: &rng)], y = nodes[Int.random(in: 0..<3, using: &rng)]
                    if x.id != y.id { _ = try? await net.sync(from: x, to: y) }
                }
            }
            for x in nodes { for y in nodes { await net.reconnect(x, y) } }
            await net.settle(nodes)
            var states: [[String]] = [], pixels: [Data] = []
            for node in nodes {
                states.append(try await state(node, did))
                let summary = try await node.engine.summary(did), ops = try await node.engine.visibleOperations(did)
                let image = DrawRender.rasterize(ops, width: summary.width, height: summary.height, background: ops.effectiveBackground(summary.background), jpeg: false, images: nil)!
                pixels.append(DrawRender.encode(image, jpeg: false)!)
            }
            XCTAssertEqual(states[0], states[1], "seed \(seed)"); XCTAssertEqual(states[1], states[2], "seed \(seed)")
            XCTAssertEqual(Set(pixels.map(DrawText.sha256)).count, 1, "seed \(seed): pixels differ")
        }
    }

    func testAssetsTransferByHashWithPlaceholderAndInterruptedTransferRestarts() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        let did = try await desktop.engine.create(title: "OLIVE Draw Image Test", width: 1200, height: 1200).id
        // Per-pixel noise (incompressible) PNG: several 256 KB chunks.
        let context = DrawRender.makeContext(width: 900, height: 900, opaque: true)!
        var rng = SeededGenerator(seed: 3)
        let pixels = context.data!.bindMemory(to: UInt64.self, capacity: context.bytesPerRow * 900 / 8)
        for i in 0..<(context.bytesPerRow * 900 / 8) { pixels[i] = rng.next() }
        let data = try DrawAssets.encodeImage(context.makeImage()!, png: true, quality: 1)
        XCTAssertGreaterThan(data.count, 3 * DrawProtocol.Limit.assetChunkBytes)
        let info = try await desktop.engine.storeAsset(data)
        _ = try await desktop.engine.append(did, .image(id: DrawText.randomID(), assetID: info.assetID, x: 100, y: 100, width: 900, height: 900, opacity: 1))
        _ = try await desktop.engine.append(did, stroke([0, 50, 1200, 50]))
        await net.setBlockAssets(true)
        _ = try? await net.sync(from: desktop, to: phone)
        let wants = try await phone.engine.wants()
        XCTAssertEqual(wants, [info.assetID])                                   // the operation came first
        let visible = try await phone.engine.visibleOperations(did)
        XCTAssertEqual(visible.count, 2)                                         // other strokes remain
        await net.setBlockAssets(false)
        await net.setKillAfter(2)                                                // phone dies after two chunks
        _ = try? await net.sync(from: desktop, to: phone)
        let restarted = await net.current(phone)
        let partial = try await restarted.engine.assetData(info.assetID)
        XCTAssertNil(partial)                                                     // no partial bytes, ever
        let staged = await restarted.engine.stagedTransfers
        XCTAssertEqual(staged, 0)
        await net.settle([desktop, restarted])
        let stored = try await restarted.engine.assetData(info.assetID)
        XCTAssertEqual(stored.map(DrawText.sha256), info.assetID)
        // Phone → desktop, then a duplicate: the bytes never travel again.
        let mine = try DrawAssets.canonicalize(pngData(50, 50, rgba: [0, 0, 1, 1]), canvasWidth: 1200, canvasHeight: 1200)
        _ = try await restarted.engine.addImage(did, mine)
        await net.settle([desktop, restarted])
        let delivered = try await desktop.engine.assetInfo(mine.info.assetID)
        XCTAssertNotNil(delivered)
        let before = await net.sentCount("asset")
        _ = try await restarted.engine.duplicate(did)
        await net.settle([desktop, restarted])
        let after = await net.sentCount("asset")
        XCTAssertEqual(before, after)
    }

    func testPurgeTombstoneBeatsAStaleOfflinePeerBothWays() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        let did = try await desktop.engine.create(title: "OLIVE Draw Offline Test", width: 100, height: 100).id
        await net.settle([desktop, phone])
        await net.disconnect(desktop, phone)
        _ = try await phone.engine.append(did, stroke([1, 1, 50, 50]))
        _ = try await phone.engine.rename(did, title: "Resurrect?")
        _ = try await desktop.engine.trash(did)
        try await desktop.engine.purge(did)
        await net.reconnect(desktop, phone)
        await net.settle([desktop, phone])
        let phonePurged = try await phone.engine.isPurged(did)
        let listed = try await desktop.engine.list(trash: false) + desktop.engine.list(trash: true)
        XCTAssertTrue(phonePurged)
        XCTAssertFalse(listed.contains { $0.id == did })
    }

    func testPermissionOffKeepsEditsPendingThenAllowCatchesUp() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        await net.setAllowed(desktop, phone, false)                           // desktop: Draw sync Off for this phone
        let did = try await phone.engine.create(title: "Pending", width: 100, height: 100).id
        _ = try await phone.engine.append(did, stroke([1, 1, 2, 2]))
        await XCTAssertThrowsErrorAsync(try await net.sync(from: phone, to: desktop)) { XCTAssertEqual(($0 as? DrawProtocol.Failure)?.code, "permission_off") }
        let none = try await desktop.engine.list(trash: false)
        XCTAssertTrue(none.isEmpty)
        let pending = try await phone.engine.pending(desktop.id)
        XCTAssertEqual(pending, 2)
        await net.setAllowed(desktop, phone, true)
        await net.settle([desktop, phone])
        let arrived = try await desktop.engine.visibleOperations(did)
        XCTAssertEqual(arrived.count, 1)
    }

    func testRestoredPeerEpochResetsCursorAndOffersEverythingAgain() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        let did = try await phone.engine.create(title: "Epoch", width: 100, height: 100).id
        _ = try await phone.engine.append(did, stroke([1, 1, 2, 2]))
        await net.settle([desktop, phone])
        let acked = try await phone.engine.peer(desktop.id).ackedSeq
        XCTAssertEqual(acked, 2)
        // The desktop restores an empty backup: a fresh store with a new epoch.
        let fresh = DrawEngine(directory: tempDirectory(), deviceID: desktop.id)
        let restored = await net.add(engine: fresh, allowAll: true)
        _ = try await net.sync(from: phone, to: restored)
        let ops = try await fresh.visibleOperations(did)
        XCTAssertEqual(ops.count, 1)                                            // everything offered again
        // The phone's own epoch renews: the desktop re-offers and nothing is duplicated.
        try await phone.engine.renewEpochForRestore()
        _ = try await net.sync(from: restored, to: phone)
        let summary = try await phone.engine.since(did)
        XCTAssertEqual(summary.records.count, 2)
    }

    func testProtocolStrictnessOnTheReceivingSide() async throws {
        let net = SimNet()
        let desktop = await net.node(), phone = await net.node()
        let good = try DrawProtocol.encodeRequest(requestID: UUID().uuidString.lowercased(), source: desktop.id, target: phone.id, operation: "hello",
                                                  arguments: .object(["versions": .array([.string("olive-draw/1")]), "schemas": .array([.int(1), .int(2)])]),
                                                  now: DrawWire.now())
        func answer(_ raw: Data, peer: String? = nil, permitted: Bool = true) async throws -> DrawProtocol.Response {
            try DrawProtocol.decodeResponse(await DrawWire.receive(engine: phone.engine, raw: raw, peer: peer ?? desktop.id, local: phone.id,
                                                                   permitted: permitted, now: DrawWire.now()))
        }
        let ok = try await answer(good)
        XCTAssertNil(ok.error)
        XCTAssertEqual(ok.result?["versions"], .array([.string("olive-draw/1")]))
        var object = try ConnectJSON.decode(good, limit: 10_000).object!
        object["extra"] = .int(1)
        let extra = try await answer(ConnectJSON.object(object).canonical)
        XCTAssertEqual(extra.error, "malformed_message")
        let wrongPeer = try await answer(good, peer: UUID().uuidString.lowercased())
        XCTAssertEqual(wrongPeer.error, "source_mismatch")
        let off = try await answer(good, permitted: false)
        XCTAssertEqual(off.error, "permission_off")
        var version = try ConnectJSON.decode(good, limit: 10_000).object!
        version["protocol_version"] = .string("olive-draw/9")
        let unsupported = try await answer(ConnectJSON.object(version).canonical)
        XCTAssertEqual(unsupported.error, "unsupported_protocol")
        let garbage = try await answer(Data("{\"protocol_version\":".utf8))
        XCTAssertEqual(garbage.error, "malformed_message")
        XCTAssertNil(garbage.requestID)
    }

    func testLargeDrawingPerformanceOnThisDevice() async throws {
        for count in [1000, 5000] {
            let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
            let did = try await engine.create(title: "OLIVE Draw Large \(count)", width: 1920, height: 1080).id
            // The desktop's own 5,000-stroke benchmark generator (drawnote.spec.ts), point for point.
            let device = UUID().uuidString.lowercased()
            let colors = ["#000000", "#e53935", "#1e63e9", "#43a047"]
            var batch: [ConnectJSON] = []
            for n in 0..<count {
                var points: [Double] = []
                for s in 0..<80 {
                    points.append(DrawQuantize.coordinate(100 + (Double(n) * 7.31 + Double(s) * 3.17).truncatingRemainder(dividingBy: 1700)))
                    points.append(DrawQuantize.coordinate(100 + (Double(n) * 3.7 + Double(s) * 1.9).truncatingRemainder(dividingBy: 880)))
                }
                let op = stroke(points, color: colors[n % 4], width: Double(2 + n % 6), opacity: n % 10 == 0 ? 0.5 : 1)
                batch.append(drawRecord("op", drawing: did, device: device, lamport: Int64(n + 2), id: op.id, body: op.json))
            }
            var started = Date()
            _ = try await engine.insertRecords(batch)
            let insert = Date().timeIntervalSince(started)
            started = Date()
            var replica = DrawReplica(drawingID: did)
            var page = try await engine.since(did)
            page.records.forEach { replica.apply($0) }
            while page.more { page = try await engine.since(did, after: page.cursor); page.records.forEach { replica.apply($0) } }
            let ops = replica.visible()
            let load = Date().timeIntervalSince(started)
            XCTAssertEqual(ops.count, count)
            started = Date()
            let context = DrawRender.makeContext(width: 1290, height: 2796)!
            let fit = DrawViewport.fit(document: CGSize(width: 1920, height: 1080), viewport: CGSize(width: 430, height: 932))
            DrawRender.replay(.init(context: context, k: fit.zoom * 3, ox: fit.offset.x * 3, oy: fit.offset.y * 3, width: 1290, height: 2796),
                              ops, from: 0, to: ops.count, images: nil)
            _ = context.makeImage()
            let render = Date().timeIntervalSince(started)
            started = Date()
            let zoomed = fit.zoomed(to: 1, around: CGPoint(x: 215, y: 466))
            DrawRender.replay(.init(context: context, k: zoomed.zoom * 3, ox: zoomed.offset.x * 3, oy: zoomed.offset.y * 3, width: 1290, height: 2796),
                              ops, from: 0, to: ops.count, images: nil)
            let zoomRender = Date().timeIntervalSince(started)
            started = Date()
            _ = try await engine.append(did, stroke([1, 1, 500, 500]))
            let edit = Date().timeIntervalSince(started)
            started = Date()
            _ = try await engine.undo(did)
            let undo = Date().timeIntervalSince(started)
            print("[draw-perf] \(count) strokes × 80 points: insert \(Int(insert * 1000)) ms, load+replica \(Int(load * 1000)) ms, " +
                  "fit render \(Int(render * 1000)) ms, 100 % render \(Int(zoomRender * 1000)) ms, one edit \(Int(edit * 1000)) ms, undo \(Int(undo * 1000)) ms")
            XCTAssertLessThan(edit, 1.0)
        }
    }
}

// MARK: - DrawSync negotiation (fake desktops on the DrawChannel seam)

/// A fake desktop behind the phone's Connect channel. `speaksDraw == false`
/// is an older desktop: it rejects the protocols probe and would close the
/// channel on a Draw frame (so a single Draw frame fails the test).
actor FakeDesktop: DrawChannel {
    let id = UUID().uuidString.lowercased()
    let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
    let phone: String
    var speaksDraw: Bool
    var allows: Bool
    private(set) var probes = 0
    private(set) var drawFrames = 0
    private(set) var closedByUnknownFrame = false
    private var inbound: (@Sendable (ConnectFrame) async -> ConnectFrame)?

    init(phone: String, speaksDraw: Bool, allows: Bool) { self.phone = phone; self.speaksDraw = speaksDraw; self.allows = allows }
    func setAllows(_ value: Bool) { allows = value }

    func exchangeFrame(kind: UInt8, id requestID: String, payload: Data) async throws -> Data {
        if kind == 1 {
            probes += 1
            let request = try ConnectJSON.decode(payload, limit: 16_384)
            guard request["capability"] == .string("connect.ping"), request["operation"] == .string("protocols") else { throw ConnectFailure.responseMalformed }
            if !speaksDraw {
                return ConnectJSON.object(["protocol_version": .string("olive-connect/1"), "request_id": .string(requestID),
                                           "state": .string("rejected"), "error": .string("unknown_operation")]).canonical
            }
            return ConnectJSON.object(["protocol_version": .string("olive-connect/1"), "request_id": .string(requestID), "state": .string("completed"),
                                       "result": .object(["pong": .bool(true), "protocols": .array([.string("olive-notes/1"), .string("olive-draw/1")])])]).canonical
        }
        guard kind == 15, speaksDraw else { closedByUnknownFrame = true; throw ConnectFailure.connectionLost }
        drawFrames += 1
        return await DrawWire.receive(engine: engine, raw: payload, peer: phone, local: id, permitted: allows, now: DrawWire.now())
    }

    func setDrawInbound(_ handler: (@Sendable (ConnectFrame) async -> ConnectFrame)?) { inbound = handler }

    /// Desktop-initiated pump (what the desktop does when a phone is allowed / announced).
    func push() async throws -> String {
        guard let inbound else { throw ConnectFailure.peerOffline }
        let send = DrawWire.sender(local: id, peer: phone, clock: { DrawWire.now() }) { _, raw in
            await inbound(ConnectFrame(kind: 15, payload: raw)).payload
        }
        return try await engine.pump(peer: phone, hello: true, send: send)
    }
}

@MainActor
final class DrawSyncNegotiationTests: XCTestCase {
    private func until(_ timeout: Double = 10, _ condition: @MainActor () async -> Bool) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline { if await condition() { return true }; try? await Task.sleep(for: .milliseconds(20)) }
        return false
    }

    private func phone() -> (DrawEngine, DrawSync, String) {
        let id = UUID().uuidString.lowercased()
        let engine = DrawEngine(directory: tempDirectory(), deviceID: id)
        let sync = DrawSync(defaults: UserDefaults(suiteName: "olive.draw.tests." + UUID().uuidString)!)
        sync.attach(engine: engine)
        return (engine, sync, id)
    }

    func testOlderDesktopIsNeverSentADrawFrameAndStaysUsableWithoutLoops() async throws {
        let (engine, sync, id) = phone()
        _ = try await engine.create(title: "Local only", width: 100, height: 100)
        let desktop = FakeDesktop(phone: id, speaksDraw: false, allows: true)
        await sync.bind(channel: desktop, local: id, peer: desktop.id)
        let unsupported = await until { sync.state == .unsupported }
        XCTAssertTrue(unsupported)
        for _ in 0..<5 { sync.kick() }
        try await Task.sleep(for: .milliseconds(300))
        let frames = await desktop.drawFrames, closed = await desktop.closedByUnknownFrame, probes = await desktop.probes
        XCTAssertEqual(frames, 0)
        XCTAssertFalse(closed)
        XCTAssertEqual(probes, 1)
        XCTAssertEqual(sync.label, "Saved on this phone · this computer’s OLIVE doesn’t support Draw yet")
    }

    func testPhoneSpeaksFirstPermissionOffThenAllowDeliversPendingDrawing() async throws {
        let (engine, sync, id) = phone()
        let did = try await engine.create(title: "OLIVE Draw Sync Test", width: 100, height: 100).id
        _ = try await engine.append(did, stroke([1, 1, 90, 90]))
        let desktop = FakeDesktop(phone: id, speaksDraw: true, allows: false)
        await sync.bind(channel: desktop, local: id, peer: desktop.id)
        let refused = await until { sync.state == .notAllowed }
        XCTAssertTrue(refused)
        let none = try await desktop.engine.list(trash: false)
        XCTAssertTrue(none.isEmpty)                                          // sync.draw Off: nothing flows
        let spoke = await desktop.drawFrames
        XCTAssertEqual(spoke, 1)                                             // the phone spoke first (hello)
        // The computer allows Draw sync: it pumps to the phone; the phone then sends its pending feed.
        await desktop.setAllows(true)
        _ = try await desktop.push()
        let arrived = await until { ((try? await desktop.engine.visibleOperations(did)) ?? []).count == 1 }
        XCTAssertTrue(arrived)
        let synced = await until { sync.state == .synced && sync.pending == 0 }
        XCTAssertTrue(synced, "\(sync.state)")
    }

    func testPhoneSwitchOffAnswersPermissionOffAndSharesNothing() async throws {
        let (engine, sync, id) = phone()
        _ = try await engine.create(title: "Private", width: 100, height: 100)
        sync.enabled = false
        let desktop = FakeDesktop(phone: id, speaksDraw: true, allows: true)
        await sync.bind(channel: desktop, local: id, peer: desktop.id)
        _ = try await desktop.engine.create(title: "From desktop", width: 100, height: 100)
        do { _ = try await desktop.push(); XCTFail("The phone shared drawings with its switch off") }
        catch { XCTAssertEqual((error as? DrawProtocol.Failure)?.code, "permission_off") }
        let received = try await engine.list(trash: false)
        XCTAssertEqual(received.map(\.title), ["Private"])
        let frames = await desktop.drawFrames
        XCTAssertEqual(frames, 0)
        XCTAssertEqual(sync.state, .off)
    }

    func testOfflineEditsAreCountedThenSentOnConnect() async throws {
        let (engine, sync, id) = phone()
        let desktop = FakeDesktop(phone: id, speaksDraw: true, allows: true)
        sync.remember(peer: desktop.id)
        let did = try await engine.create(title: "Offline", width: 100, height: 100).id
        _ = try await engine.append(did, stroke([1, 1, 2, 2]))
        let counted = await until { sync.refreshState(); return sync.pending == 2 }
        XCTAssertTrue(counted)
        XCTAssertEqual(sync.state, .offline)
        XCTAssertTrue(sync.label.hasPrefix("Offline — 2 edits waiting"))
        await sync.bind(channel: desktop, local: id, peer: desktop.id)
        let synced = await until { sync.state == .synced && sync.pending == 0 }
        XCTAssertTrue(synced)
        let ops = try await desktop.engine.visibleOperations(did)
        XCTAssertEqual(ops.count, 1)
    }
}

// MARK: - helpers

func XCTAssertThrowsErrorAsync<T>(_ expression: @autoclosure () async throws -> T, file: StaticString = #filePath, line: UInt = #line,
                                  _ handler: (Error) -> Void = { _ in }) async {
    do { _ = try await expression(); XCTFail("Expected an error", file: file, line: line) }
    catch { handler(error) }
}

// MARK: - Editor model (commit path, remote updates, export)

@MainActor
final class DrawEditorModelTests: XCTestCase {
    private func until(_ timeout: Double = 10, _ condition: @MainActor () -> Bool) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline { if condition() { return true }; try? await Task.sleep(for: .milliseconds(20)) }
        return false
    }

    func testCommitRemoteUpdateUndoAndExportThroughTheEditorModel() async throws {
        let engine = DrawEngine(directory: tempDirectory(), deviceID: UUID().uuidString.lowercased())
        let did = try await engine.create(title: "OLIVE Draw Editor Test", width: 400, height: 300).id
        let editor = DrawEditorModel(drawingID: did, engine: engine, defaults: UserDefaults(suiteName: "olive.draw.tests." + UUID().uuidString)!)
        let canvas = DrawCanvasUIView(frame: CGRect(x: 0, y: 0, width: 390, height: 500))
        editor.attach(canvas: canvas)
        await editor.load()
        XCTAssertEqual(editor.visibleCount, 0)
        editor.canvasCommit(stroke([10, 10, 300, 200]))
        let committed = await until { editor.visibleCount == 1 && editor.saveState == .saved }
        XCTAssertTrue(committed, "visible \(editor.visibleCount) state \(editor.saveState)")
        XCTAssertEqual(canvas.accessibilityValue?.hasPrefix("1 visible edit"), true, canvas.accessibilityValue ?? "")
        XCTAssertEqual(editor.undoCount, 1)
        // A remote record arrives: the open editor shows it without reopening.
        let remote = stroke([0, 0, 50, 50], color: "#e53935")
        _ = try await engine.insertRecords([drawRecord("op", drawing: did, device: UUID().uuidString.lowercased(), lamport: 3, id: remote.id, body: remote.json)],
                                           source: UUID().uuidString.lowercased())
        editor.remoteChanged()
        let pulled = await until { editor.visibleCount == 2 }
        XCTAssertTrue(pulled)
        editor.undo()
        let undone = await until { editor.visibleCount == 1 && editor.undoCount == 0 && editor.redoCount == 1 }
        XCTAssertTrue(undone)
        editor.setBackground("transparent")
        let transparent = await until { editor.background == "transparent" }
        XCTAssertTrue(transparent)
        let png = await editor.export(jpeg: false)
        let url = try XCTUnwrap(png)
        XCTAssertEqual(url.lastPathComponent, "OLIVE Draw Editor Test.png")
        let exported = try XCTUnwrap(DrawAssets.decode(try Data(contentsOf: url)))
        XCTAssertEqual([exported.width, exported.height], [400, 300])            // document resolution, not zoom
        XCTAssertEqual(DrawRender.pixel(exported, x: 390, y: 290)[3], 0)
        let jpeg = await editor.export(jpeg: true)
        XCTAssertEqual(try XCTUnwrap(jpeg).pathExtension, "jpg")
    }
}
