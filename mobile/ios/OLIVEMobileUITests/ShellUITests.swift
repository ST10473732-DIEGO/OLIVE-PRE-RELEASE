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
    func testLaunchAndHome() {
        XCTAssertTrue(app.staticTexts["home.heading"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["home.ask"].exists)
        XCTAssertTrue(app.staticTexts["Not connected"].exists)
        capture("OLIVE Home")
    }
    func testRootNavigationAndDevicesEmptyState() {
        app.buttons["home.devices"].tap()
        XCTAssertTrue(app.staticTexts["No paired devices"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Pairing is coming next"].exists)
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
