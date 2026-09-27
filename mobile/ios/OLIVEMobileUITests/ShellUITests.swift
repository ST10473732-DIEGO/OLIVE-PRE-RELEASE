import XCTest

/// Real production session, explicitly shared synthetic CachyOS workspace only.
/// No offline UI fixture or simulated background grant is used.
@MainActor
final class RealStudioBackgroundAcceptanceTests: XCTestCase {
    func testRealOwnedFileBackgroundTransfer() throws {
        let id = ProcessInfo.processInfo.environment["OLIVE_C93_FILE_UI_ID"] ?? ""
        try XCTSkipUnless(UUID(uuidString: id)?.uuidString.lowercased() == id, "Explicit prepared owned transfer ID required")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let app = XCUIApplication(); app.launchArguments = ["--c93-transport-trace", "--c93-select-owned-file", id]; app.launch()
        app.tabBars.buttons["Home"].tap()
        let files = app.buttons["Files"]
        for _ in 0..<5 { if files.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(files.waitForExistence(timeout: 10)); files.tap()
        let send = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'files.send.'")).firstMatch
        XCTAssertTrue(send.waitForExistence(timeout: 10))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: send)], timeout: 25), .completed)
        let transfer = String(send.identifier.dropFirst("files.send.".count))
        print("C93 FILE BACKGROUND TRANSFER \(transfer)")
        send.tap() // One explicit user action; no retries.
        app.navigationBars.buttons["Home"].tap()
        for _ in 0..<5 { if app.staticTexts["Background continuation active"].isHittable { break }; app.swipeUp() }
        XCTAssertTrue(app.staticTexts["Background continuation active"].waitForExistence(timeout: 15))
        let started = Date(); XCUIDevice.shared.press(.home)
        // Observe completion and idle session release before foreground reconnect.
        // The owned 64 MiB fixture has taken up to 70 seconds on the real LAN.
        let elapsed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in Date().timeIntervalSince(started) >= 90 }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [elapsed], timeout: 95), .completed)
        XCTAssertNotEqual(app.state, .runningForeground)
        app.activate()
        // Reacquire navigation after the active-work card has disappeared and
        // foreground reconnect has settled; do not reuse its old hit snapshot.
        app.tabBars.buttons["Devices"].tap()
        XCTAssertTrue(app.staticTexts["Connected"].waitForExistence(timeout: 25))
        app.tabBars.buttons["Home"].tap()
        let returnToFiles = app.buttons.matching(identifier: "Files").firstMatch
        for _ in 0..<5 { if returnToFiles.isHittable { break }; app.swipeUp() }
        returnToFiles.tap()
        XCTAssertTrue(app.navigationBars["Files"].waitForExistence(timeout: 5))
        let state = app.staticTexts["files.state." + transfer]
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'completed'"), object: state)], timeout: 45), .completed,
            "Expected C6 verified completion; observed \(state.label). Expiration/interruption is retained for diagnosis, never retried.")
    }
    func testRealSelectedChatTombstoneAcrossRelaunch() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_CHAT_TOMBSTONE_UI_ACCEPTANCE"] == "1", "Explicit synthetic real Chat tombstone phase only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let app = XCUIApplication()
        for _ in 0..<2 {
            app.launch()
            app.tabBars.buttons["Home"].tap()
            let selected = app.buttons["Selected Chat"]
            for _ in 0..<6 { if selected.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(selected.waitForExistence(timeout: 10)); selected.tap()
            let sync = app.buttons["Sync Chat"]
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: sync)], timeout: 25), .completed)
            sync.tap()
            XCTAssertTrue(app.staticTexts["Sync complete"].waitForExistence(timeout: 20))
            // Only the named, owned fixture: never open private historic chats.
            let read = app.buttons["sync.read.1d20bcdd-bb21-497e-88df-9d43933f78e4"]
            for _ in 0..<6 { if read.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(read.waitForExistence(timeout: 10)); read.tap()
            XCTAssertTrue(app.staticTexts["Reply with C93 SECOND"].waitForExistence(timeout: 10))
            XCTAssertFalse(app.staticTexts["Reply with C93 FIRST"].exists)
            app.terminate()
        }
    }
    func testRealBackgroundRunAndCancel() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C93_STUDIO_UI_ACCEPTANCE"] == "1", "Explicit physical iPhone/CachyOS acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--c93-transport-trace"]
        app.launch()
        func tap(_ label: String) {
            let button = app.buttons[label]
            for _ in 0..<8 { if button.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(button.waitForExistence(timeout: 10), label)
            button.tap()
        }
        func status(_ label: String, timeout: TimeInterval) {
            // The result may include the protocol's structured test counters.
            let predicate = NSPredicate(format: "label == %@ OR label BEGINSWITH %@", label, label + " · ")
            let expected = XCTNSPredicateExpectation(predicate: predicate, object: app.staticTexts["studio.status"])
            XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: timeout), .completed, "Expected \(label); observed \(app.staticTexts["studio.status"].label)")
        }
        app.tabBars.buttons["Home"].tap()
        tap("Remote Studio")
        let refresh = app.buttons["Refresh workspaces"]
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: refresh)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 25), .completed)
        refresh.tap()
        XCTAssertTrue(app.buttons["C93 Acceptance Shared"].waitForExistence(timeout: 10))
        tap("C93 Acceptance Shared")
        XCTAssertTrue(app.buttons["notes.txt"].waitForExistence(timeout: 10))
        tap("Run")
        XCTAssertTrue(app.buttons["Cancel operation"].waitForExistence(timeout: 10))
        app.navigationBars.buttons["Home"].tap()
        for _ in 0..<5 { if app.staticTexts["Background continuation active"].isHittable { break }; app.swipeUp() }
        XCTAssertTrue(app.staticTexts["Background continuation active"].waitForExistence(timeout: 15), "Real iOS continued-processing grant required")
        let began = Date()
        XCUIDevice.shared.press(.home)
        // Yield on the test runner, not OLIVE's process. The real application
        // remains backgrounded and subject to normal iOS lifecycle behavior.
        let elapsed = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in Date().timeIntervalSince(began) >= 65 }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [elapsed], timeout: 70), .completed)
        XCTAssertNotEqual(app.state, .runningForeground)
        app.activate()
        tap("Remote Studio")
        for _ in 0..<5 { if app.staticTexts["studio.status"].isHittable { break }; app.swipeUp() }
        status("completed", timeout: 30)
        let evidence = XCTAttachment(string: "Real C8 Run: iOS grant visible, backgrounded for at least 65 seconds, foreground result completed. One explicit Run tap.")
        evidence.lifetime = .keepAlways; add(evidence)
        // A fresh, explicit operation proves recovery, then uses normal mobile
        // cancellation. No automatic retry or second start is permitted.
        tap("Run")
        XCTAssertTrue(app.buttons["Cancel operation"].waitForExistence(timeout: 10))
        tap("Cancel operation")
        status("cancelled", timeout: 20)
        XCTAssertFalse(app.buttons["Cancel operation"].exists)
    }
}

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
    func testScrollToLatestButton() {
        app.terminate(); app.launchArguments += ["--ui-test-long-chat"]; app.launch()
        tab("Chat")
        let jump = app.buttons["chat.scrollToBottom"]
        let chat = app.scrollViews.firstMatch
        let latest = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Synthetic answer 24, line 1.'")).firstMatch
        func expectJump(_ visible: Bool, _ step: String, file: StaticString = #filePath, line: UInt = #line) {
            let predicate = NSPredicate(format: visible ? "exists == true AND hittable == true" : "exists == false")
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: jump)], timeout: 4), .completed,
                           "\(step): expected jump button \(visible ? "visible" : "hidden")", file: file, line: line)
        }
        func returnWithJump(_ step: String) {
            jump.tap()
            expectJump(false, step + " after tap")
            XCTAssertTrue(latest.waitForExistence(timeout: 3), step + ": latest answer on screen")
        }
        XCTAssertTrue(chat.waitForExistence(timeout: 5))
        expectJump(false, "Opens at latest")
        XCTAssertTrue(latest.exists)
        for cycle in 1...4 {
            chat.swipeDown(velocity: .slow)
            expectJump(true, "Cycle \(cycle) small scroll")
            returnWithJump("Cycle \(cycle) small scroll")
            for _ in 0..<12 { chat.swipeDown(velocity: .fast) }
            expectJump(true, "Cycle \(cycle) top")
            XCTAssertTrue(app.staticTexts["Synthetic question 1"].exists, "Reached the top")
            returnWithJump("Cycle \(cycle) top")
        }
        chat.swipeDown(velocity: .slow)
        expectJump(true, "Before manual return")
        for _ in 0..<3 { chat.swipeUp(velocity: .fast) }
        expectJump(false, "Manual scroll back to latest")
        capture("OLIVE Chat at latest")
        XCUIDevice.shared.orientation = .landscapeLeft
        expectJump(false, "Landscape at latest")
        chat.swipeDown(velocity: .slow)
        expectJump(true, "Landscape small scroll")
        capture("OLIVE Chat jump button landscape")
        returnWithJump("Landscape")
        for _ in 0..<15 { chat.swipeDown(velocity: .fast) }
        expectJump(true, "Landscape top")
        returnWithJump("Landscape top")
    }
    func testClearChat() {
        XCTAssertFalse(app.buttons["chat.clear"].exists)
        app.terminate(); app.launchArguments += ["--ui-test-long-chat"]; app.launch()
        tab("Chat")
        let clear = app.buttons["chat.clear"]
        XCTAssertTrue(clear.waitForExistence(timeout: 5))
        clear.tap()
        let confirm = app.buttons["chat.clearConfirm"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 3))
        capture("OLIVE Clear chat confirmation")
        confirm.tap()
        XCTAssertTrue(app.descendants(matching: .any)["chat.empty"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Synthetic question 24"].exists)
        XCTAssertFalse(clear.exists)
        XCTAssertFalse(app.buttons["chat.scrollToBottom"].exists)
        capture("OLIVE Chat cleared")
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
