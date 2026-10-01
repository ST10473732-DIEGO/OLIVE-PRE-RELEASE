import XCTest
import UIKit

/// OLIVE DrawNote › Draw on the phone, driven through the real UI with real
/// touch synthesis. Synthetic drawings only; skipped unless explicitly enabled.
@MainActor
struct DrawUI {
    let app: XCUIApplication
    var canvas: XCUIElement { app.descendants(matching: .any)["draw.canvas"] }

    func log(_ line: String) { print("DRAW-UI \(Date().timeIntervalSince1970) \(line)") }

    /// DrawNote tab › Draw section, at the drawing list.
    func openDraw() {
        app.tabBars.buttons["DrawNote"].tap()
        if canvas.exists { back() }
        let section = app.segmentedControls["drawnote.section"].buttons["Draw"]
        XCTAssertTrue(section.waitForExistence(timeout: 10))
        if !section.isSelected { section.tap() }
        XCTAssertTrue(app.navigationBars["OLIVE DrawNote"].waitForExistence(timeout: 10) || app.navigationBars["Recently Deleted"].exists)
        if app.navigationBars["Recently Deleted"].exists { app.buttons["draw.trashToggle"].tap() }
    }

    func back() {
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.navigationBars["OLIVE DrawNote"].waitForExistence(timeout: 10) || app.navigationBars["Recently Deleted"].exists)
    }

    /// A drawing row by exact title (its label is "Title, drawing, W by H").
    func row(_ title: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", title + ", drawing")).firstMatch
    }
    func cell(_ title: String) -> XCUIElement {
        app.cells.containing(NSPredicate(format: "label BEGINSWITH %@", title + ", drawing")).firstMatch
    }

    func create(_ title: String, preset: String = "800 × 600") {
        app.buttons["draw.new"].tap()
        let item = app.buttons[preset]
        XCTAssertTrue(item.waitForExistence(timeout: 5))
        item.tap()
        XCTAssertTrue(canvas.waitForExistence(timeout: 10))
        rename(title)
    }

    func open(_ title: String, timeout: TimeInterval = 30) {
        let target = row(title)
        XCTAssertTrue(target.waitForExistence(timeout: timeout), "\(title) did not appear")
        target.tap()
        XCTAssertTrue(canvas.waitForExistence(timeout: 10))
    }

    func more(_ item: String) {
        app.buttons["draw.more"].tap()
        let button = app.buttons[item]
        XCTAssertTrue(button.waitForExistence(timeout: 5), "\(item) missing from Drawing actions")
        button.tap()
    }

    func rename(_ title: String) {
        more("Rename")
        let field = app.textFields["draw.renameField"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        if let value = field.value as? String, !value.isEmpty { field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: value.count + 2)) }
        field.typeText(title + "\n")                                   // return commits (Save does the same)
        if app.buttons["draw.renameSave"].waitForExistence(timeout: 1) { app.buttons["draw.renameSave"].tap() }
        XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 10), "title \(title) not shown")
    }

    /// One-finger drag across the canvas (normalized coordinates): one stroke.
    func drag(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double) {
        let start = canvas.coordinate(withNormalizedOffset: CGVector(dx: x1, dy: y1))
        let end = canvas.coordinate(withNormalizedOffset: CGVector(dx: x2, dy: y2))
        start.press(forDuration: 0.05, thenDragTo: end, withVelocity: 600, thenHoldForDuration: 0.05)
    }

    var edits: Int {
        let value = canvas.value as? String ?? ""
        return Int(value.split(separator: " ").first ?? "") ?? -1
    }
    var zoom: Int {
        let value = canvas.value as? String ?? ""
        guard let range = value.range(of: "zoom ") else { return -1 }
        return Int(value[range.upperBound...].split(separator: " ").first ?? "") ?? -1
    }

    @discardableResult
    func expectEdits(_ count: Int, timeout: TimeInterval = 10) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if edits == count { return true }
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))
        }
        XCTFail("expected \(count) visible edits, canvas says \(canvas.value as? String ?? "?")")
        return false
    }

    func brush(color: String? = nil, size: Double? = nil, opacity: Double? = nil) {
        app.buttons["draw.brush"].tap()
        if let color {
            let swatch = app.buttons["Colour \(color)"]
            XCTAssertTrue(swatch.waitForExistence(timeout: 5)); swatch.tap()
        }
        if let size { app.sliders["draw.size"].adjust(toNormalizedSliderPosition: size) }
        if let opacity { app.sliders["draw.opacity"].adjust(toNormalizedSliderPosition: opacity) }
        app.swipeDown(velocity: .fast)   // dismiss the sheet
        if app.sliders["draw.size"].exists { app.otherElements["PopoverDismissRegion"].firstMatch.tap() }
        XCTAssertTrue(canvas.waitForExistence(timeout: 5))
    }

    func syncStatus() -> String {
        let line = app.descendants(matching: .any)["draw.sync"]
        return line.waitForExistence(timeout: 10) ? line.label : "(no status)"
    }

    func shareAndDismiss(_ item: String) -> Bool {
        more(item)
        let sheet = app.otherElements["ActivityListView"]
        let shown = sheet.waitForExistence(timeout: 15) || app.navigationBars["UIActivityContentView"].waitForExistence(timeout: 2)
        if app.buttons["Close"].exists { app.buttons["Close"].tap() } else { app.swipeDown(velocity: .fast) }
        _ = canvas.waitForExistence(timeout: 5)
        return shown
    }
}

/// Isolated UI profile (`--ui-test-session`): no pairing, no Connect, no real drawings.
final class DrawUIAcceptanceTests: XCTestCase {
    @MainActor func testDrawLocalFlowSurvivesRelaunch() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_DRAW_UI_ACCEPTANCE"] == "1", "Explicit OLIVE Draw UI acceptance only")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--ui-test-session", "draw-" + UUID().uuidString.lowercased(), "--ui-test-draw-fixture"]
        app.launch()
        let ui = DrawUI(app: app)
        ui.openDraw()
        XCTAssertTrue(app.staticTexts["No drawings yet"].waitForExistence(timeout: 10))
        XCTAssertTrue(ui.syncStatus().contains("Saved on this phone"))
        ui.create("OLIVE Draw UI Test")
        let fitZoom = ui.zoom
        XCTAssertGreaterThan(fitZoom, 0)
        XCTAssertEqual(ui.edits, 0)
        // A fresh profile starts with the default brush: black, 8 px, opaque.
        XCTAssertEqual(app.buttons["draw.brush"].value as? String, "Black, 8 px, 100 percent opacity")
        // Pen (black), then a red, wider, translucent line (all inside the page).
        ui.drag(0.15, 0.38, 0.85, 0.38); ui.expectEdits(1)
        ui.brush(color: "Red", size: 0.6, opacity: 0.5)
        let brushValue = app.buttons["draw.brush"].value as? String ?? ""
        XCTAssertTrue(brushValue.hasPrefix("Red,") && brushValue.hasSuffix("50 percent opacity") && !brushValue.contains(" 8 px"), brushValue)
        ui.drag(0.15, 0.50, 0.85, 0.50); ui.expectEdits(2)
        // Eraser through both lines.
        app.buttons["draw.eraser"].tap()
        XCTAssertTrue(app.buttons["draw.eraser"].isSelected)
        ui.drag(0.5, 0.3, 0.5, 0.6); ui.expectEdits(3)
        app.buttons["draw.pen"].tap()
        // Undo / Redo (this phone's own edits).
        app.buttons["draw.undo"].tap(); ui.expectEdits(2)
        app.buttons["draw.redo"].tap(); ui.expectEdits(3)
        // Pinch zoom, then Fit. (A two-finger pan cannot be synthesized by XCUITest.)
        ui.canvas.pinch(withScale: 2.5, velocity: 2)
        let zoomed = ui.zoom
        XCTAssertGreaterThan(zoomed, fitZoom, "pinch did not zoom")
        XCTAssertEqual(ui.edits, 3, "navigation must never draw")
        app.buttons["draw.zoom"].tap()
        let deadline = Date().addingTimeInterval(5)
        while ui.zoom != fitZoom && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
        XCTAssertEqual(ui.zoom, fitZoom)
        // Background: transparent (an operation).
        ui.more("Transparent"); ui.expectEdits(4)
        // Import a synthetic image (same pipeline as Photos/Files), then draw over it.
        ui.more("Synthetic test image"); ui.expectEdits(5, timeout: 15)
        XCTAssertTrue(app.descendants(matching: .any)["draw.notice"].waitForExistence(timeout: 5))
        ui.drag(0.2, 0.62, 0.8, 0.62); ui.expectEdits(6)
        RunLoop.current.run(until: Date().addingTimeInterval(1))   // let the off-main render land
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "draw-editor"; shot.lifetime = .keepAlways; add(shot)
        // Export / share (PNG and JPEG) through the standard share sheet.
        XCTAssertTrue(ui.shareAndDismiss("Share PNG"), "PNG share sheet did not appear")
        XCTAssertTrue(ui.shareAndDismiss("Share JPEG"), "JPEG share sheet did not appear")
        XCTAssertTrue(app.descendants(matching: .any)["draw.status"].label.contains("Saved on this phone"))
        ui.back()
        XCTAssertTrue(ui.row("OLIVE Draw UI Test").waitForExistence(timeout: 5))
        // Duplicate, delete, Recently Deleted, restore.
        ui.cell("OLIVE Draw UI Test").swipeLeft()
        app.buttons["Duplicate"].tap()
        XCTAssertTrue(ui.row("OLIVE Draw UI Test (copy)").waitForExistence(timeout: 10))
        ui.cell("OLIVE Draw UI Test (copy)").swipeLeft()
        app.buttons["Delete"].tap()
        XCTAssertFalse(ui.row("OLIVE Draw UI Test (copy)").waitForExistence(timeout: 2))
        app.buttons["draw.trashToggle"].tap()
        XCTAssertTrue(ui.row("OLIVE Draw UI Test (copy)").waitForExistence(timeout: 10))
        ui.cell("OLIVE Draw UI Test (copy)").swipeLeft()
        app.buttons["Restore"].tap()
        app.buttons["draw.trashToggle"].tap()
        XCTAssertTrue(ui.row("OLIVE Draw UI Test (copy)").waitForExistence(timeout: 10))
        // Full relaunch: drawing, image, undo history and the DrawNote section persist.
        app.terminate()
        app.launch()
        app.tabBars.buttons["DrawNote"].tap()
        XCTAssertTrue(app.segmentedControls["drawnote.section"].buttons["Draw"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.segmentedControls["drawnote.section"].buttons["Draw"].isSelected, "DrawNote did not reopen Draw")
        ui.open("OLIVE Draw UI Test")
        ui.expectEdits(6, timeout: 15)
        app.buttons["draw.undo"].tap(); ui.expectEdits(5)           // phone-local history survived the restart
        ui.drag(0.2, 0.44, 0.8, 0.44); ui.expectEdits(6)            // still editable
        RunLoop.current.run(until: Date().addingTimeInterval(1))
        let after = XCTAttachment(screenshot: app.screenshot()); after.name = "draw-after-relaunch"; after.lifetime = .keepAlways; add(after)
        ui.back()
        // Notes is still the Notes app inside DrawNote.
        app.segmentedControls["drawnote.section"].buttons["Notes"].tap()
        XCTAssertTrue(app.staticTexts["No notes yet"].waitForExistence(timeout: 10))
    }
}

/// Real iPhone ↔ computer OLIVE Draw acceptance against the existing pairing
/// (or a separate test host). Steps come from TEST_RUNNER_OLIVE_DRAW_LIVE_STEPS,
/// e.g. "draw|open:OLIVE Draw Sync Test|stroke:0.2,0.3,0.8,0.3|edits:3|undo".
/// It never pairs, unpairs or changes permissions, and only opens named drawings.
final class DrawLiveAcceptanceTests: XCTestCase {
    @MainActor func testLiveDrawSteps() throws {
        let environment = ProcessInfo.processInfo.environment
        try XCTSkipUnless(environment["OLIVE_DRAW_LIVE_ACCEPTANCE"] == "1", "Explicit real iPhone <-> computer OLIVE Draw acceptance only")
        let steps = (environment["OLIVE_DRAW_LIVE_STEPS"] ?? "").split(separator: "|").map(String.init)
        let app = XCUIApplication()
        if let extra = environment["OLIVE_DRAW_LIVE_ARGS"], !extra.isEmpty { app.launchArguments = extra.split(separator: " ").map(String.init) }
        app.launch()
        let ui = DrawUI(app: app)
        let wait = Double(environment["OLIVE_DRAW_LIVE_WAIT"] ?? "60") ?? 60
        for step in steps {
            let parts = step.split(separator: ":", maxSplits: 1).map(String.init)
            let name = parts[0], value = parts.count > 1 ? parts[1] : ""
            let numbers = value.split(separator: ",").compactMap { Double($0) }
            ui.log("step \(name) \(value)")
            switch name {
            case "draw": ui.openDraw()
            case "create": ui.openDraw(); ui.create(value)
            case "open": if !(ui.canvas.exists && app.navigationBars[value].exists) { ui.openDraw(); ui.open(value, timeout: wait) }
            case "listed": ui.openDraw(); XCTAssertTrue(ui.row(value).waitForExistence(timeout: wait), "\(value) not listed")
            case "absent":
                ui.openDraw()
                let deadline = Date().addingTimeInterval(wait)
                while ui.row(value).exists && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.25)) }
                XCTAssertFalse(ui.row(value).exists, "\(value) still listed")
            case "stroke": ui.drag(numbers[0], numbers[1], numbers[2], numbers[3])
            case "erase": app.buttons["draw.eraser"].tap(); ui.drag(numbers[0], numbers[1], numbers[2], numbers[3]); app.buttons["draw.pen"].tap()
            case "color": ui.brush(color: value)
            case "undo", "redo":
                // A system banner can swallow a toolbar tap: confirm the edit count moved, retry once.
                let before = ui.edits
                for _ in 0..<2 {
                    app.buttons["draw.\(name)"].tap()
                    let deadline = Date().addingTimeInterval(4)
                    while ui.edits == before && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.1)) }
                    if ui.edits != before { break }
                    ui.log("\(name) tap had no effect; retrying")
                }
            case "edits": ui.expectEdits(Int(value) ?? -1, timeout: wait)
            case "background": ui.more(value)
            case "import-fixture": ui.more("Synthetic test image")
            case "rename": ui.rename(value)
            case "trash": ui.openDraw(); ui.cell(value).swipeLeft(); app.buttons["Delete"].tap()
            case "restore": ui.openDraw(); app.buttons["draw.trashToggle"].tap(); ui.cell(value).swipeLeft(); app.buttons["Restore"].tap(); app.buttons["draw.trashToggle"].tap()
            case "back": if ui.canvas.exists { ui.back() }
            case "status": ui.log("status=\(ui.syncStatus())")
            case "wait-status":
                let deadline = Date().addingTimeInterval(wait)
                var label = ""
                repeat {
                    label = app.descendants(matching: .any)["draw.status"].exists
                        ? app.descendants(matching: .any)["draw.status"].label : ui.syncStatus()
                    if label.contains(value) { break }
                    RunLoop.current.run(until: Date().addingTimeInterval(0.25))
                } while Date() < deadline
                ui.log("status=\(label)")
                XCTAssertTrue(label.contains(value), "status \(label) lacks \(value)")
            case "sleep": RunLoop.current.run(until: Date().addingTimeInterval(numbers.first ?? 1))
            case "suspend":
                XCUIDevice.shared.press(.home)
                RunLoop.current.run(until: Date().addingTimeInterval(numbers.first ?? 5))
                app.activate()
            case "relaunch": app.terminate(); app.launch()
            case "screenshot":
                let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "draw-" + value; shot.lifetime = .keepAlways; add(shot)
            default: XCTFail("Unknown step \(name)")
            }
        }
    }
}

/// Pairs the phone's SEPARATE acceptance identity (`--c92-pairing-check`: its own
/// Keychain item and trust store) with a temporary Mac test host
/// (tests/fixtures/draw_phone_test_host.py). The user's real pairing is never
/// read or changed. The offer is typed into the paste field; the comparison
/// value is confirmed on both sides.
final class DrawTestHostPairingTests: XCTestCase {
    @MainActor func testPairAcceptanceIdentityWithTestHost() throws {
        let offer = ProcessInfo.processInfo.environment["OLIVE_DRAW_TEST_HOST_OFFER"] ?? ""
        try XCTSkipUnless(!offer.isEmpty, "Explicit test-host pairing only")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check"]
        app.launch()
        app.tabBars.buttons["Devices"].tap()
        let pair = app.buttons.matching(identifier: "Pair computer").firstMatch
        XCTAssertTrue(pair.waitForExistence(timeout: 15)); pair.tap()
        let disclosure = app.buttons["Paste a public pairing code"]
        XCTAssertTrue(disclosure.waitForExistence(timeout: 10)); disclosure.tap()
        let editor = app.textViews["pairing.offer"]
        XCTAssertTrue(editor.waitForExistence(timeout: 10))
        editor.tap()
        editor.typeText(offer)
        app.buttons["Begin pairing"].tap()
        let comparison = app.staticTexts["pairing.comparison"]
        XCTAssertTrue(comparison.waitForExistence(timeout: 60), "no comparison value")
        let value = comparison.label
        let field = app.textFields["Value displayed on your computer"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap(); field.typeText(value)
        app.buttons["Values match"].tap()
        XCTAssertTrue(app.staticTexts["Paired"].waitForExistence(timeout: 60), "pairing did not complete")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Connected")).firstMatch.waitForExistence(timeout: 60), "not connected to the test host")
    }
}

/// Layout checks on the phone: landscape rotation keeps the document (only the
/// viewport moves) and the Draw chrome stays usable at accessibility text sizes.
final class DrawUILayoutTests: XCTestCase {
    @MainActor func testRotationAndLargeTextKeepDrawUsable() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_DRAW_UI_ACCEPTANCE"] == "1", "Explicit OLIVE Draw UI acceptance only")
        let app = XCUIApplication()
        app.launchArguments = ["--ui-test-session", "draw-layout-" + UUID().uuidString.lowercased(), "--ui-test-draw-fixture",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"]
        app.launch()
        let ui = DrawUI(app: app)
        ui.openDraw()
        let library = XCTAttachment(screenshot: app.screenshot()); library.name = "draw-library-large-text"; library.lifetime = .keepAlways; add(library)
        ui.create("OLIVE Draw Layout Test")
        ui.drag(0.2, 0.45, 0.8, 0.45); ui.expectEdits(1)
        for id in ["draw.pen", "draw.eraser", "draw.brush", "draw.zoom", "draw.undo", "draw.more"] {
            XCTAssertTrue(app.buttons[id].isHittable, "\(id) not reachable at large text")
        }
        let portrait = XCTAttachment(screenshot: app.screenshot()); portrait.name = "draw-editor-large-text"; portrait.lifetime = .keepAlways; add(portrait)
        XCUIDevice.shared.orientation = .landscapeLeft
        RunLoop.current.run(until: Date().addingTimeInterval(2))
        XCTAssertEqual(ui.edits, 1, "rotation must not change the drawing")
        for id in ["draw.pen", "draw.undo", "draw.more"] { XCTAssertTrue(app.buttons[id].isHittable, "\(id) not reachable in landscape") }
        ui.drag(0.3, 0.5, 0.7, 0.5); ui.expectEdits(2)
        let landscape = XCTAttachment(screenshot: app.screenshot()); landscape.name = "draw-editor-landscape"; landscape.lifetime = .keepAlways; add(landscape)
        XCUIDevice.shared.orientation = .portrait
        RunLoop.current.run(until: Date().addingTimeInterval(2))
        XCTAssertEqual(ui.edits, 2)
    }
}
