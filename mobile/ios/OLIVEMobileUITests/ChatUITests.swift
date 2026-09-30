import XCTest

/// Drives OLIVE Chat. Isolated sessions only; synthetic content only.
struct ChatUI {
    let app: XCUIApplication

    static func launch(_ extra: [String] = [], seed: Bool = true) -> ChatUI {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-test-session", "chat-" + UUID().uuidString.lowercased(), "--ui-test-chat-fixture",
                               "--ui-test-synthetic-pickers"] + (seed ? ["--ui-test-seed-drawnote"] : []) + extra
        app.launch()
        let ui = ChatUI(app: app)
        ui.openChat()
        return ui
    }

    func openChat() {
        let tab = app.tabBars.buttons["Chat"]
        XCTAssertTrue(tab.waitForExistence(timeout: 15)); tab.tap()
    }
    var composer: XCUIElement {
        let view = app.textViews["chat.composer"]
        return view.exists ? view : app.textFields["chat.composer"]
    }
    func type(_ text: String) {
        XCTAssertTrue(composer.waitForExistence(timeout: 10))
        composer.tap(); composer.typeText(text)
        if app.buttons["chat.dismissKeyboard"].exists { app.buttons["chat.dismissKeyboard"].tap() }
    }
    func mode(_ id: String) {
        let button = app.buttons["chat.mode"]
        XCTAssertTrue(button.waitForExistence(timeout: 10)); button.tap()
        let row = app.buttons["chat.mode." + id]
        // Rows below the fold are created lazily; scroll the sheet until the row exists.
        for _ in 0..<4 where !(row.waitForExistence(timeout: 2) && row.isHittable) { app.collectionViews.firstMatch.swipeUp() }
        XCTAssertTrue(row.exists, id)
        row.tap()
        XCTAssertTrue(app.buttons["chat.mode"].waitForExistence(timeout: 5))
    }
    /// A row in the open mode sheet, scrolled into existence.
    func modeRow(_ id: String) -> XCUIElement {
        let row = app.buttons["chat.mode." + id]
        for _ in 0..<4 where !(row.waitForExistence(timeout: 2) && row.isHittable) { app.collectionViews.firstMatch.swipeUp() }
        return row
    }
    func attach(_ source: String) {
        let plus = app.buttons["chat.attach"]
        XCTAssertTrue(plus.waitForExistence(timeout: 10)); XCTAssertTrue(plus.isEnabled)
        plus.tap()
        let item = app.buttons["chat.attach." + source]
        XCTAssertTrue(item.waitForExistence(timeout: 5), "menu item \(source)"); item.tap()
    }
    func send(timeout: Double = 60) {
        let send = app.buttons["chat.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 10))
        let enabled = NSPredicate(format: "isEnabled == true")
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: enabled, object: send)], timeout: 15)
        XCTAssertTrue(send.isEnabled, "Send disabled"); send.tap()
        let idle = app.buttons["chat.send"]
        XCTAssertTrue(idle.waitForExistence(timeout: timeout), "request did not finish")
    }
    func lastStatus() -> String {
        app.staticTexts.matching(identifier: "chat.message.status").allElementsBoundByIndex.last?.label ?? ""
    }
    func screenshot(_ test: XCTestCase, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = name; shot.lifetime = .keepAlways; test.add(shot)
    }
}

/// Deterministic Chat UI on the phone against the in-process fixture computer
/// (real olive-chat/1 client, wire validation, attachments, downloads and players).
/// Not a model and not the real desktop.
final class ChatUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    @MainActor func testModeSelectorGroupsAllNineModesAccessibly() {
        let ui = ChatUI.launch([], seed: false)
        ui.app.buttons["chat.mode"].tap()
        for id in ["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"] {
            let row = ui.app.buttons["chat.mode." + id]
            for _ in 0..<4 where !row.waitForExistence(timeout: 1) { ui.app.collectionViews.firstMatch.swipeUp() }
            XCTAssertTrue(row.exists, id)
        }
        ui.app.collectionViews.firstMatch.swipeDown()
        XCTAssertEqual(ui.app.buttons["chat.mode.normal"].value as? String, "Selected")
        XCTAssertFalse(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'qwen' OR label CONTAINS[c] 'flux' OR label CONTAINS[c] 'ltx'")).firstMatch.exists)
        ui.screenshot(self, "chat-mode-selector")
        ui.modeRow("audio").tap()
        XCTAssertTrue(ui.app.buttons["chat.mode"].waitForExistence(timeout: 5)); sleep(1)
        ui.app.buttons["chat.mode"].tap()
        XCTAssertTrue(ui.app.buttons["chat.mode.done"].waitForExistence(timeout: 5))
        let voice = ui.app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Voice'")).firstMatch
        for _ in 0..<4 where !voice.waitForExistence(timeout: 1) { ui.app.collectionViews.firstMatch.swipeUp() }
        XCTAssertTrue(voice.exists, "AUDIO voices advertised by the computer are offered")
        ui.app.buttons["chat.mode.done"].tap()
        XCTAssertTrue(ui.app.buttons["chat.mode"].label.contains("AUDIO"))
    }

    @MainActor func testPlusMenuChipsAndModeRevalidation() {
        let ui = ChatUI.launch([], seed: false)
        ui.app.buttons["chat.attach"].tap()
        for source in ["photos", "files", "notes", "drawings"] { XCTAssertTrue(ui.app.buttons["chat.attach." + source].exists, source) }
        ui.app.buttons["chat.attach.photos"].tap()
        let chip = ui.app.descendants(matching: .any)["chat.attachment.photo"]
        XCTAssertTrue(chip.waitForExistence(timeout: 15))
        ui.type("Describe the colours")
        ui.mode("video")
        XCTAssertTrue(ui.app.staticTexts["chat.composerNotice"].waitForExistence(timeout: 5))
        XCTAssertTrue(ui.app.staticTexts["chat.composerNotice"].label.contains("VIDEO currently supports text prompts only"))
        XCTAssertFalse(ui.app.buttons["chat.send"].isEnabled)
        ui.screenshot(self, "chat-video-rejects-attachment")
        ui.app.buttons["chat.attachment.remove"].firstMatch.tap()
        XCTAssertFalse(chip.waitForExistence(timeout: 2))
        XCTAssertTrue(ui.app.buttons["chat.send"].isEnabled)
    }

    @MainActor func testNormalWithPhotoAndNoteSnapshot() {
        let ui = ChatUI.launch()
        ui.attach("notes")
        let note = ui.app.buttons["chat.pick.note"].firstMatch
        XCTAssertTrue(note.waitForExistence(timeout: 20)); note.tap()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.note"].waitForExistence(timeout: 10))
        ui.type("Summarise the attached note in one sentence.")
        ui.send()
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Attachment Test” received'")).firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue(ui.app.staticTexts["chat.message.attribution"].firstMatch.label.contains("NORMAL"))
    }

    @MainActor func testDeepPDFCitationsAndDrawReimagine() {
        let ui = ChatUI.launch()
        ui.mode("deep")
        ui.attach("files")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.file"].waitForExistence(timeout: 15))
        ui.type("What is the unique test phrase?")
        ui.send()
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'amber-falcon-7'")).firstMatch.waitForExistence(timeout: 10))
        ui.app.buttons["chat.sources"].firstMatch.tap()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.source"].firstMatch.waitForExistence(timeout: 5))
        ui.screenshot(self, "chat-deep-citation")
        ui.mode("reimagine")
        ui.attach("drawings")
        let drawing = ui.app.buttons["chat.pick.drawing"].firstMatch
        XCTAssertTrue(drawing.waitForExistence(timeout: 20)); drawing.tap()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.draw"].waitForExistence(timeout: 15))
        ui.type("Make the background darker")
        ui.send()
        let image = ui.app.buttons["chat.artifact.image.open"].firstMatch
        XCTAssertTrue(image.waitForExistence(timeout: 20)); image.tap()
        XCTAssertTrue(ui.app.images["chat.viewer.image"].waitForExistence(timeout: 10))
        ui.app.images["chat.viewer.image"].pinch(withScale: 2, velocity: 1)
        ui.screenshot(self, "chat-image-viewer")
        XCTAssertTrue(ui.app.buttons["chat.artifact.share"].firstMatch.exists)
        ui.app.buttons["chat.viewer.done"].tap()
    }

    @MainActor func testAudioAndVideoPlayers() {
        let ui = ChatUI.launch([], seed: false)
        ui.mode("audio")
        ui.type("Say: OLIVE mobile audio test.")
        ui.send()
        let play = ui.app.buttons["chat.audio.play"].firstMatch
        XCTAssertTrue(play.waitForExistence(timeout: 20))
        XCTAssertTrue(ui.app.staticTexts["chat.audio.duration"].firstMatch.label.hasSuffix("0:02"))
        play.tap()
        XCTAssertTrue(ui.app.buttons["Pause"].waitForExistence(timeout: 3))
        ui.app.buttons["Pause"].tap()
        XCTAssertTrue(ui.app.sliders["chat.audio.seek"].firstMatch.exists)
        // The Share Sheet opens for the verified local file (then dismissed; nothing is shared).
        ui.app.buttons["chat.artifact.share"].firstMatch.tap()
        let sheet = ui.app.otherElements["ActivityListView"]
        XCTAssertTrue(sheet.waitForExistence(timeout: 10), "Share Sheet did not open")
        ui.screenshot(self, "chat-share-sheet")
        let close = ui.app.buttons["Close"].firstMatch
        if close.exists { close.tap() } else { ui.app.swipeDown() }
        XCTAssertTrue(ui.app.buttons["chat.audio.play"].firstMatch.waitForExistence(timeout: 10))
        ui.mode("video")
        ui.type("A short calm synthetic scene")
        ui.send()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 30))
        ui.screenshot(self, "chat-video-player")
    }

    @MainActor func testNowSourcesOpenSafely() {
        let ui = ChatUI.launch([], seed: false)
        ui.mode("now")
        ui.type("What is the weather in Cape Town right now?")
        ui.send()
        ui.app.buttons["chat.sources"].firstMatch.tap()
        let open = ui.app.buttons["chat.source.open"].firstMatch
        XCTAssertTrue(open.waitForExistence(timeout: 5))
        XCTAssertTrue(open.label.contains("Synthetic weather bulletin"))
        // Opens in the system browser (public synthetic test domain), never inside OLIVE.
        open.tap()
        // The system opens the link in the user's default browser; OLIVE itself leaves the foreground.
        XCTAssertTrue(ui.app.wait(for: .runningBackground, timeout: 15), "the source link was not handed to the system")
        ui.app.activate()
        XCTAssertTrue(ui.app.buttons.matching(NSPredicate(format: "label CONTAINS 'example.org'")).firstMatch.exists || open.exists)
        ui.screenshot(self, "chat-now-sources")
    }

    @MainActor func testStopUnavailableOfflineAndOlderComputer() {
        var ui = ChatUI.launch([], seed: false)
        ui.mode("video")
        ui.type("A slow synthetic scene")
        ui.app.buttons["chat.send"].tap()
        let stop = ui.app.buttons["chat.stop"]
        XCTAssertTrue(stop.waitForExistence(timeout: 10)); sleep(2); stop.tap()
        XCTAssertTrue(ui.app.buttons["chat.send"].waitForExistence(timeout: 15))
        XCTAssertTrue(ui.app.staticTexts["Generation stopped."].waitForExistence(timeout: 5))
        XCTAssertFalse(ui.app.descendants(matching: .any)["chat.video.player"].exists, "no late result after Stop")
        ui.app.terminate()
        ui = ChatUI.launch(["--ui-test-video-unavailable"], seed: false)
        ui.app.buttons["chat.mode"].tap()
        XCTAssertTrue((ui.modeRow("video").value as? String ?? "").contains("Not set up"))
        ui.app.buttons["chat.mode.done"].tap()
        ui.app.terminate()
        ui = ChatUI.launch(["--ui-test-chat-offline"], seed: false)
        ui.type("Hello")
        XCTAssertFalse(ui.app.buttons["chat.send"].isEnabled)
        XCTAssertTrue(ui.app.staticTexts["chat.composerNotice"].label.contains("offline"))
        ui.app.terminate()
        ui = ChatUI.launch(["--ui-test-chat-legacy"], seed: false)
        ui.app.buttons["chat.mode"].tap()
        XCTAssertTrue((ui.modeRow("reimagine").value as? String ?? "").contains("doesn't support this mode yet"))
        ui.screenshot(self, "chat-older-computer")
    }

    @MainActor func testLargeTextAndLandscapeKeepComposerUsable() {
        let ui = ChatUI.launch(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"], seed: false)
        ui.app.buttons["chat.attach"].tap(); ui.app.buttons["chat.attach.photos"].tap()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        ui.type("Large text check")
        XCTAssertTrue(ui.app.buttons["chat.send"].isHittable); XCTAssertTrue(ui.app.buttons["chat.attach"].isHittable)
        ui.screenshot(self, "chat-large-text")
        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(2)
        XCTAssertTrue(ui.app.buttons["chat.send"].isHittable)
        ui.screenshot(self, "chat-landscape")
        XCUIDevice.shared.orientation = .portrait
    }
}

/// OPT-IN physical acceptance against the Mac TEST HOST (tests/fixtures/draw_phone_test_host.py --chat):
/// production Connect, olive-chat/1, staging and receipts over the real Wi-Fi channel, with the
/// deterministic TEST runtime. Uses the separate acceptance identity (--c92-pairing-check).
/// This is PHYSICAL IPHONE ↔ TEST HOST verification, never real-model verification.
final class ChatTestHostTests: XCTestCase {
    private var enabled: Bool { ProcessInfo.processInfo.environment["OLIVE_CHAT_TEST_HOST"] == "1" }

    private func launch() -> ChatUI {
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check", "--ui-test-synthetic-pickers", "--ui-test-seed-drawnote"]
        app.launch()
        let ui = ChatUI(app: app); ui.openChat()
        let mode = app.buttons["chat.mode"]
        XCTAssertTrue(mode.waitForExistence(timeout: 30))
        // Wait until the computer's mode matrix arrived (the + button needs it).
        let ready = NSPredicate(format: "isEnabled == true")
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: ready, object: app.buttons["chat.attach"])], timeout: 60)
        XCTAssertTrue(app.buttons["chat.attach"].isEnabled, "olive-chat/1 not negotiated with the test host")
        return ui
    }

    /// Pairs the separate acceptance identity (never the user's pairing) with a fresh test host.
    @MainActor func testPairAcceptanceIdentityWithChatTestHost() throws {
        let offer = ProcessInfo.processInfo.environment["OLIVE_CHAT_TEST_HOST_OFFER"] ?? ""
        try XCTSkipUnless(!offer.isEmpty, "Explicit test-host pairing only")
        continueAfterFailure = false
        let reset = XCUIApplication()
        reset.launchArguments = ["--c92-cleanup-pairing-check"]  // Removes only the acceptance identity and its folder.
        reset.launch(); sleep(3); reset.terminate()
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check"]
        app.launch()
        app.tabBars.buttons["Devices"].tap()
        let pair = app.buttons.matching(identifier: "Pair computer").firstMatch
        XCTAssertTrue(pair.waitForExistence(timeout: 15)); pair.tap()
        let disclosure = app.buttons["Paste a public pairing code"]
        XCTAssertTrue(disclosure.waitForExistence(timeout: 10)); disclosure.tap()
        let editor = app.textViews["pairing.offer"]
        XCTAssertTrue(editor.waitForExistence(timeout: 10)); editor.tap(); editor.typeText(offer)
        app.buttons["Begin pairing"].tap()
        let comparison = app.staticTexts["pairing.comparison"]
        XCTAssertTrue(comparison.waitForExistence(timeout: 60), "no comparison value")
        let field = app.textFields["Value displayed on your computer"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText(comparison.label)
        app.buttons["Values match"].tap()
        XCTAssertTrue(app.staticTexts["Paired"].waitForExistence(timeout: 60), "pairing did not complete")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.staticTexts["Connected"].waitForExistence(timeout: 60), "not connected to the test host")
    }

    @MainActor func testAllNineModesOverConnect() throws {
        try XCTSkipUnless(enabled, "Explicit test-host acceptance only")
        continueAfterFailure = false
        let ui = launch()
        let cases: [(String, String, String)] = [
            ("fast", "Reply with exactly: fast-mobile-ready", "fast-mobile-ready"),
            ("normal", "Reply with exactly: normal-mobile-ready", "normal-mobile-ready"),
            ("max", "Reply with exactly: max-mobile-ready", "max-mobile-ready"),
            ("uncensored", "Write a short story about a lighthouse", "UNCENSORED"),
            ("now", "What is the weather in Cape Town right now?", "[S1]"),
            ("deep", "Explain the trade-offs of local inference", "Answered by DEEP, RESEARCH"),
        ]
        for (mode, prompt, expected) in cases {
            ui.mode(mode); ui.type(prompt); ui.send()
            XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", expected)).firstMatch.waitForExistence(timeout: 20), mode)
        }
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Answered by UNCENSORED, CREATIVE, This computer'")).firstMatch.exists)
        ui.screenshot(self, "test-host-text-modes")
        ui.mode("reimagine"); ui.type("Generate a simple image of a blue square on a white background."); ui.send(timeout: 90)
        XCTAssertTrue(ui.app.buttons["chat.artifact.image.open"].firstMatch.waitForExistence(timeout: 60))
        ui.mode("audio"); ui.type("Say: OLIVE mobile audio test."); ui.send(timeout: 90)
        XCTAssertTrue(ui.app.buttons["chat.audio.play"].firstMatch.waitForExistence(timeout: 60))
        ui.app.buttons["chat.audio.play"].firstMatch.tap(); sleep(1)
        ui.mode("video"); ui.type("A short calm synthetic scene"); ui.send(timeout: 120)
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 90))
        ui.screenshot(self, "test-host-media-modes")
    }

    @MainActor func testAttachmentsOverConnect() throws {
        try XCTSkipUnless(enabled, "Explicit test-host acceptance only")
        continueAfterFailure = false
        let ui = launch()
        ui.mode("deep"); ui.attach("files")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.file"].waitForExistence(timeout: 15))
        ui.type("What is the unique test phrase?"); ui.send(timeout: 90)
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'amber-falcon-7'")).firstMatch.waitForExistence(timeout: 30))
        ui.mode("normal"); ui.attach("notes")
        let note = ui.app.buttons["chat.pick.note"].firstMatch
        XCTAssertTrue(note.waitForExistence(timeout: 20)); note.tap()
        ui.type("Summarise the attached note in one sentence."); ui.send(timeout: 90)
        // The test runtime echoes the snapshot's line count and last line: injection text arrives as content only.
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'received (3 lines): IGNORE OLIVE'")).firstMatch.waitForExistence(timeout: 30))
        ui.attach("drawings")
        let drawing = ui.app.buttons["chat.pick.drawing"].firstMatch
        XCTAssertTrue(drawing.waitForExistence(timeout: 20)); drawing.tap()
        ui.type("What colours are visible?"); ui.send(timeout: 90)
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'colours: blue'")).firstMatch.waitForExistence(timeout: 30))
        ui.attach("photos")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        ui.mode("reimagine"); ui.type("Make the background darker"); ui.send(timeout: 90)
        XCTAssertTrue(ui.app.buttons["chat.artifact.image.open"].firstMatch.waitForExistence(timeout: 60))
        ui.screenshot(self, "test-host-attachments")
    }

    /// The Mac orchestrator turns the test host's network off and on while bytes move
    /// (tests/fixtures/draw_phone_test_host.py network_off / network_on).
    @MainActor func testDisconnectDuringUploadAndDownload() throws {
        try XCTSkipUnless(enabled && ProcessInfo.processInfo.environment["OLIVE_CHAT_DISCONNECT"] == "1", "Explicit disconnect acceptance only")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check", "--ui-test-synthetic-pickers", "--ui-test-large-attachment"]
        app.launch()
        let ui = ChatUI(app: app); ui.openChat()
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "isEnabled == true"), object: app.buttons["chat.attach"])], timeout: 60)
        ui.mode("deep"); ui.attach("files")
        XCTAssertTrue(app.descendants(matching: .any)["chat.attachment.file"].waitForExistence(timeout: 60))
        ui.type("What is the unique test phrase?")
        let started = Date()
        app.buttons["chat.send"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'amber-falcon-7'")).firstMatch.waitForExistence(timeout: 300),
                      "upload did not resume after the computer came back")
        NSLog("OLIVE-DIAG upload+answer seconds=%.1f", Date().timeIntervalSince(started))
        ui.mode("video"); ui.type("A large synthetic scene")
        let video = Date()
        app.buttons["chat.send"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 400),
                      "download did not resume after the computer came back")
        NSLog("OLIVE-DIAG video request+transfer seconds=%.1f", Date().timeIntervalSince(video))
        ui.screenshot(self, "test-host-after-disconnects")
    }

    /// The Mac orchestrator restarts the test host's OLIVE service (same profile and identity)
    /// while a request runs. The phone must say the outcome is unknown and never resend.
    @MainActor func testComputerRestartDuringRequest() throws {
        try XCTSkipUnless(enabled && ProcessInfo.processInfo.environment["OLIVE_CHAT_RESTART"] == "1", "Explicit restart acceptance only")
        continueAfterFailure = false
        let ui = launch()
        ui.mode("normal"); ui.type("slow reply for a computer restart, long enough to still be streaming when it happens")
        ui.app.buttons["chat.send"].tap()
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'restarted while working on this' OR label CONTAINS 'stopped this request when OLIVE restarted'")).firstMatch.waitForExistence(timeout: 180))
        ui.screenshot(self, "test-host-computer-restart")
    }

    /// Steps are driven from outside (host restarts, Wi-Fi-like drops) via TEST_RUNNER_OLIVE_CHAT_STEP.
    @MainActor func testStopAndRelaunchRecovery() throws {
        try XCTSkipUnless(enabled, "Explicit test-host acceptance only")
        continueAfterFailure = false
        var ui = launch()
        ui.mode("video"); ui.type("A slow synthetic scene"); ui.app.buttons["chat.send"].tap()
        let stop = ui.app.buttons["chat.stop"]
        XCTAssertTrue(stop.waitForExistence(timeout: 20)); sleep(3); stop.tap()
        XCTAssertTrue(ui.app.staticTexts["Generation stopped."].waitForExistence(timeout: 30))
        // A slow text request, then the app is killed mid-answer and relaunched: the computer
        // keeps the job; the phone recovers it by status, never by sending it again.
        ui.mode("normal"); ui.type("slow reply for relaunch recovery, long enough to still be streaming"); ui.app.buttons["chat.send"].tap()
        XCTAssertTrue(ui.app.buttons["chat.stop"].waitForExistence(timeout: 20)); sleep(1)
        ui.app.terminate()
        ui = launch()
        XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'long enough to still be streaming'")).firstMatch.waitForExistence(timeout: 60))
        ui.screenshot(self, "test-host-relaunch-recovery")
        // Earlier media reopens from this iPhone without regenerating.
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.video.player"].firstMatch.exists || ui.app.buttons["chat.audio.play"].firstMatch.exists
                      || ui.app.buttons["chat.artifact.image.open"].firstMatch.exists)
    }
}

/// OPT-IN physical acceptance against the user's REAL paired OLIVE computer, using the
/// normal app profile and its existing pairing (OLIVE_CHAT_REAL_DESKTOP=1). Harmless
/// synthetic prompts only. Refuses to run if the composer holds unsent user text.
final class ChatRealDesktopTests: XCTestCase {
    @MainActor func testTextModesAndModeNegotiationOnRealComputer() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_CHAT_REAL_DESKTOP"] == "1", "Explicit real-desktop acceptance only")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launch()
        let ui = ChatUI(app: app); ui.openChat()
        let existing = (ui.composer.value as? String) ?? ""
        try XCTSkipUnless(existing.isEmpty || existing == "Message OLIVE", "The composer holds unsent text; not touching the user's draft")
        let connected = NSPredicate(format: "label CONTAINS 'Connected' OR label CONTAINS 'Completed' OR label == ''")
        _ = connected
        XCTAssertTrue(app.buttons["chat.mode"].waitForExistence(timeout: 60))
        sleep(10) // Negotiation (protocol probe + capabilities) completes shortly after connecting.
        app.buttons["chat.mode"].tap()
        var matrix: [String] = []
        for id in ["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"] {
            let value = (ui.modeRow(id).value as? String) ?? ""
            matrix.append("\(id)=\(value.isEmpty ? "available" : value)")
        }
        NSLog("OLIVE-DIAG real-computer modes %@", matrix.joined(separator: "; "))
        ui.screenshot(self, "real-computer-mode-matrix")
        app.buttons["chat.mode.done"].tap()
        for mode in ["fast", "normal", "max"] {
            ui.mode(mode)
            ui.type("Reply with exactly: \(mode)-mobile-ready")
            let started = Date()
            ui.send(timeout: 400)
            let answer = app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] %@", "\(mode)-mobile-ready")).allElementsBoundByIndex
            NSLog("OLIVE-DIAG real %@ seconds=%.1f matches=%d status=%@", mode, Date().timeIntervalSince(started), answer.count, ui.lastStatus())
            XCTAssertGreaterThanOrEqual(answer.count, 2, "\(mode): the prompt and a matching answer")
            let attribution = "Answered by \(mode.uppercased()), This computer"
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == %@", attribution)).firstMatch.exists, attribution)
        }
        ui.screenshot(self, "real-computer-text-modes")
    }
}
