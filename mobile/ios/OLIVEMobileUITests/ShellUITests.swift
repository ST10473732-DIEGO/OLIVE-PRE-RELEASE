import XCTest

@MainActor
final class ShellUITests: XCTestCase {
    private var app: XCUIApplication!
    override func setUp() async throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--ui-test-session", UUID().uuidString]
        app.launch()
    }
    override func tearDown() async throws {
        XCUIDevice.shared.orientation = .portrait
        app.terminate()
    }
    private func tab(_ name: String) { app.tabBars.buttons[name].tap() }
    private func capture(_ name: String) {
        // Capture only while OLIVE is foreground, including its system keyboard.
        // XCUIApplication screenshots crop rotated windows on this Xcode version.
        XCTAssertEqual(app.state, .runningForeground)
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
    func testCompanionNavigationOffline() {
        for (label, title) in [("Today", "Today"), ("Files", "Files"), ("Remote Studio", "Studio"), ("Selected Chat", "Selected Chat")] {
            let link = app.buttons[label]
            for _ in 0..<4 { if link.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(link.waitForExistence(timeout: 3)); link.tap()
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 3))
            capture("OLIVE " + title)
            app.navigationBars.buttons.firstMatch.tap()
        }
    }
    func testTaskEditorShowsBothConflictVersionsWithoutConnection() {
        app.terminate()
        app.launchArguments += ["--ui-test-sync-conflict"]
        app.launch()
        let today = app.buttons["Today"]
        for _ in 0..<4 { if today.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(today.waitForExistence(timeout: 3)); today.tap()
        let task = app.buttons.containing(.staticText, identifier: "UI phone version").firstMatch
        XCTAssertTrue(task.waitForExistence(timeout: 3)); task.tap()
        let review = app.buttons["today.editorConflict"]
        for _ in 0..<5 { if review.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(review.waitForExistence(timeout: 3)); review.tap()
        XCTAssertTrue(app.staticTexts["UI phone version"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["UI desktop version"].exists)
        XCTAssertFalse(app.buttons["Use incoming version"].isEnabled)
        capture("OLIVE synthetic offline conflict review")
    }
    func testVerifiedFileRequiresExplicitExportAndStudioConflictIsReadOnlyOffline() {
        app.terminate(); app.launchArguments += ["--ui-test-companion"]; app.launch()
        let files = app.buttons["Files"]
        for _ in 0..<5 { if files.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(files.waitForExistence(timeout: 3)); files.tap()
        XCTAssertTrue(app.staticTexts["Transfer verified · Ready to Save"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["files.export"].exists)
        XCTAssertFalse(app.buttons["Choose file to send"].isEnabled)
        capture("OLIVE synthetic verified quarantine")
        app.navigationBars.buttons.firstMatch.tap()
        let studio = app.buttons["Remote Studio"]
        for _ in 0..<5 { if studio.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(studio.waitForExistence(timeout: 3)); studio.tap()
        let editor = app.textViews["studio.editor"]
        for _ in 0..<5 { if editor.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(editor.exists); XCTAssertEqual(editor.value as? String, "let value = 2")
        let save = app.buttons["Save with revision check"]
        for _ in 0..<5 { if save.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(save.exists); XCTAssertFalse(save.isEnabled)
        for name in ["Build", "Test", "Run"] {
            let action = app.buttons[name]
            for _ in 0..<5 { if action.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(action.exists); XCTAssertFalse(action.isEnabled)
        }
        XCTAssertFalse(app.buttons["Terminal"].exists)
        capture("OLIVE synthetic Studio conflict and unavailable actions")
    }
    func testLaunchAndHome() {
        XCTAssertTrue(app.staticTexts["home.heading"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["home.ask"].exists)
        XCTAssertTrue(app.staticTexts["Not connected"].exists)
        capture("OLIVE Home")
    }
    func testRootNavigationAndDevicesEmptyState() {
        app.buttons["home.devices"].tap()
        XCTAssertTrue(app.staticTexts["No paired devices"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Pair an OLIVE computer to chat."].exists)
        capture("OLIVE Devices")
        tab("Chat")
        XCTAssertTrue(app.textViews["chat.composer"].exists || app.textFields["chat.composer"].exists)
        tab("Home")
        XCTAssertTrue(app.buttons["home.ask"].exists)
    }
    private var composer: XCUIElement {
        let view = app.textViews["chat.composer"]
        return view.exists ? view : app.textFields["chat.composer"]
    }
    func testComposerMultilineAndDisabledSend() {
        app.buttons["home.ask"].tap()
        composer.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertGreaterThan(app.keyboards.firstMatch.frame.height, 100)
        capture("OLIVE Keyboard before typing")
        composer.typeText("A thought\nAnother line")
        XCTAssertEqual(composer.value as? String, "A thought\nAnother line")
        XCTAssertFalse(app.buttons["chat.send"].isEnabled)
        capture("OLIVE Chat keyboard and draft")
        app.buttons["chat.dismissKeyboard"].tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        tab("Devices")
        tab("Chat")
        XCTAssertEqual(composer.value as? String, "A thought\nAnother line")
    }
    func testSettingsAboutAndDismiss() {
        app.buttons["settings.open"].tap()
        XCTAssertTrue(app.staticTexts["About"].waitForExistence(timeout: 5))
        let version = app.descendants(matching: .any).matching(identifier: "settings.version").firstMatch
        XCTAssertEqual(version.value as? String, "0.1.0 (1)")
        let connection = app.descendants(matching: .any).matching(identifier: "settings.connection").firstMatch
        XCTAssertEqual(connection.value as? String, "Not connected")
        capture("OLIVE Settings")
        app.buttons["settings.done"].tap()
        XCTAssertTrue(app.buttons["home.ask"].waitForExistence(timeout: 5))
    }
    func testRelaunchAndBackgroundPreserveDraft() {
        tab("Chat")
        composer.tap()
        composer.typeText("Local relaunch draft")
        app.buttons["chat.dismissKeyboard"].tap()
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertEqual(composer.value as? String, "Local relaunch draft")
        app.terminate()
        app.launch()
        XCTAssertTrue(composer.waitForExistence(timeout: 10))
        XCTAssertEqual(composer.value as? String, "Local relaunch draft")
        XCTAssertFalse(app.buttons["chat.send"].isEnabled)
    }
    func testLandscapeNavigationAndComposer() {
        XCUIDevice.shared.orientation = .landscapeLeft
        tab("Chat")
        XCTAssertTrue(composer.waitForExistence(timeout: 5))
        composer.tap()
        composer.typeText("Landscape draft")
        XCTAssertEqual(composer.value as? String, "Landscape draft")
        capture("OLIVE Landscape keyboard")
        app.buttons["chat.dismissKeyboard"].tap()
        capture("OLIVE Landscape")
        tab("Devices")
        XCTAssertTrue(app.staticTexts["No paired devices"].waitForExistence(timeout: 5))
    }
    func testAccessibilityTextSize() {
        app.terminate()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.buttons["home.ask"].waitForExistence(timeout: 5))
        tab("Chat")
        XCTAssertTrue(composer.exists)
        composer.tap()
        composer.typeText("Large text draft")
        XCTAssertEqual(composer.value as? String, "Large text draft")
        capture("OLIVE Accessibility keyboard")
        app.buttons["chat.dismissKeyboard"].tap()
        capture("OLIVE Accessibility text size")
    }
}

/// Opt in explicitly: TEST_RUNNER_OLIVE_C92_LAN_ACCEPTANCE=1 xcodebuild ...
/// Uses the normal app and actual LAN; no simulated discovery or peers.
@MainActor
final class RealLANAcceptanceTests: XCTestCase {
    func testRealLANDiscovery() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C92_LAN_ACCEPTANCE"] == "1", "Explicit real-LAN acceptance only")
        let app = XCUIApplication()
        let monitor = addUIInterruptionMonitor(withDescription: "OLIVE Local Network permission") { alert in
            if alert.buttons["Allow"].exists { alert.buttons["Allow"].tap(); return true }
            if alert.buttons["OK"].exists { alert.buttons["OK"].tap(); return true }
            return false
        }
        defer { removeUIInterruptionMonitor(monitor) }
        app.launch()
        app.tabBars.buttons["Devices"].tap()
        let started = Date()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "devices.nearby").firstMatch.waitForExistence(timeout: 20))
        let evidence = XCTAttachment(string: "Actual Bonjour discovery visible after \(Date().timeIntervalSince(started)) seconds")
        evidence.lifetime = .keepAlways; add(evidence)
        XCTAssertEqual(app.state, .runningForeground)
        let image = XCTAttachment(screenshot: app.screenshot()); image.lifetime = .keepAlways; add(image)
    }
}
