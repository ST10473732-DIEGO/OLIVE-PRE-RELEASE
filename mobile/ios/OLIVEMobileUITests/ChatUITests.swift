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
    /// Picks a VIDEO length from the Duration sheet ("auto", "20", …).
    @MainActor func videoLength(_ option: String) {
        let length = app.buttons["chat.videoDuration"]
        XCTAssertTrue(length.waitForExistence(timeout: 10), "no Duration control"); length.tap()
        let row = app.buttons["chat.videoDuration.option." + option]
        for _ in 0..<4 where !(row.waitForExistence(timeout: 2) && row.isHittable) { app.collectionViews.firstMatch.swipeUp() }
        XCTAssertTrue(row.exists, option); row.tap()
        XCTAssertTrue(length.waitForExistence(timeout: 5))
    }
    @MainActor var videoPlayers: Int { app.descendants(matching: .any).matching(identifier: "chat.video.player").count }
    /// After Send: follows the running request, logging each distinct status line, until it ends.
    @MainActor func follow(timeout: TimeInterval) -> [String] {
        XCTAssertTrue(app.buttons["chat.stop"].waitForExistence(timeout: 30), "request did not start")
        var seen: [String] = []
        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            let status = lastStatus()
            if !status.isEmpty, seen.last != status {
                seen.append(status); NSLog("OLIVE-DIAG t=%.0fs status=%@", Date().timeIntervalSince(start), status)
            }
            if app.buttons["chat.send"].exists && !app.buttons["chat.stop"].exists { break }
            sleep(2)
        }
        NSLog("OLIVE-DIAG request seconds=%.0f final=%@", Date().timeIntervalSince(start), lastStatus())
        return seen
    }
    /// The on-device AVPlayer item's loaded duration and audio tracks (DEBUG `--ui-test-diagnostics`).
    @MainActor func lastPlayerDiagnostic() -> (seconds: Double, audioTracks: Int) {
        let d = playerDiagnostic(); return (d.seconds, d.audioTracks)
    }
    @MainActor func playerDiagnostic() -> (seconds: Double, audioTracks: Int, position: Double, rate: Double, session: String) {
        let player = app.descendants(matching: .any).matching(identifier: "chat.video.player").allElementsBoundByIndex.last
        var value = ""
        for _ in 0..<20 { value = (player?.value as? String) ?? ""; if !value.isEmpty { break }; sleep(1) }
        NSLog("OLIVE-DIAG player %@", value)
        func field(_ key: String) -> String? {
            value.components(separatedBy: "; ").first { $0.hasPrefix(key + "=") }.map { String($0.dropFirst(key.count + 1)) }
        }
        return (Double(field("avplayer_duration") ?? "") ?? 0, Int(field("audio_tracks") ?? "") ?? 0,
                Double(field("position") ?? "") ?? 0, Double(field("rate") ?? "") ?? 0, field("session") ?? "")
    }
    @MainActor func clearComposer() {
        // The accessibility value is truncated, so delete from the end until only the placeholder is left.
        for _ in 0..<4 {
            let text = (composer.value as? String) ?? ""
            if text.isEmpty || text == "Message OLIVE" { break }
            composer.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.9)).tap()
            composer.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 80))
        }
        if app.buttons["chat.dismissKeyboard"].exists { app.buttons["chat.dismissKeyboard"].tap() }
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
        // An older computer without VIDEO image-to-video: the photo is refused truthfully.
        let ui = ChatUI.launch(["--ui-test-legacy-video"], seed: false)
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

    @MainActor func testVideoLengthAutoCustomAndImageToVideo() {
        let ui = ChatUI.launch([], seed: false)
        ui.mode("video")
        let length = ui.app.buttons["chat.videoDuration"]
        XCTAssertTrue(length.waitForExistence(timeout: 5))
        XCTAssertTrue(length.label.contains("Auto"), length.label)
        ui.type("Create a 20 second cinematic shot of rain")
        XCTAssertTrue(length.label.contains("Auto · 20 s"), "a length in the message is understood without the picker")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.videoPlan"].label.contains("10 generation segments"))
        length.tap()
        for option in ["auto", "2", "5", "10", "20", "30", "60"] {
            XCTAssertTrue(ui.app.buttons["chat.videoDuration.option." + option].waitForExistence(timeout: 5), option)
        }
        let custom = ui.app.textFields["chat.videoDuration.custom"]
        // The sheet opens at medium height; the Custom row is built once scrolled into view.
        for _ in 0..<4 where !(custom.waitForExistence(timeout: 2) && custom.isHittable) { ui.app.collectionViews.firstMatch.swipeUp() }
        custom.tap(); custom.typeText("37")
        ui.screenshot(self, "chat-video-length-sheet")
        ui.app.buttons["chat.videoDuration.apply"].tap()
        XCTAssertTrue(length.waitForExistence(timeout: 5)); XCTAssertTrue(length.label.contains("37 s"), length.label)
        ui.app.buttons["chat.attach"].tap(); ui.app.buttons["chat.attach.photos"].tap()
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.videoPlan"].label.contains("Image → Video"))
        XCTAssertTrue(ui.app.buttons["chat.send"].isEnabled)
        ui.screenshot(self, "chat-video-image-to-video")
        ui.send(timeout: 60)
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 30))
    }

    @MainActor func testVideoCustomLengthWithLargeTextAndVoiceOverLabels() {
        let ui = ChatUI.launch(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"], seed: false)
        ui.mode("video")
        let length = ui.app.buttons["chat.videoDuration"]
        XCTAssertTrue(length.waitForExistence(timeout: 5)); XCTAssertTrue(length.isHittable)
        XCTAssertTrue(length.label.hasPrefix("Video length, Auto"), length.label)
        ui.screenshot(self, "chat-video-duration-large-text")
        length.tap()
        for option in ["auto", "2", "5", "10", "20", "30", "60"] {
            let row = ui.app.buttons["chat.videoDuration.option." + option]
            for _ in 0..<4 where !(row.waitForExistence(timeout: 2) && row.isHittable) { ui.app.collectionViews.firstMatch.swipeUp() }
            XCTAssertTrue(row.exists, option)
        }
        XCTAssertTrue(ui.app.buttons["chat.videoDuration.option.60"].label.contains("1 min"))
        let custom = ui.app.textFields["chat.videoDuration.custom"]
        for _ in 0..<4 where !(custom.waitForExistence(timeout: 2) && custom.isHittable) { ui.app.collectionViews.firstMatch.swipeUp() }
        XCTAssertEqual(custom.label, "Custom length")
        custom.tap(); custom.typeText("13")
        let apply = ui.app.buttons["chat.videoDuration.apply"]
        XCTAssertTrue(apply.waitForExistence(timeout: 5)); XCTAssertEqual(apply.label, "Use 13 s")
        ui.screenshot(self, "chat-video-custom-13-large-text")
        apply.tap()
        XCTAssertTrue(length.waitForExistence(timeout: 5)); XCTAssertEqual(length.label, "Video length, 13 s")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.videoPlan"].label.contains("7 generation segments"))
        XCTAssertTrue(ui.app.buttons["chat.send"].isHittable)
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

    /// Host started with --chat-animate (long-form VIDEO, 10 segments) and a 20 s synthetic MP4. The Mac
    /// orchestrator takes the computer off the network mid-generation and again mid-download; the phone
    /// must follow the same job to one artifact, never resubmitting it.
    @MainActor func testLongVideoRecoversAcrossDisconnects() throws {
        try XCTSkipUnless(enabled && ProcessInfo.processInfo.environment["OLIVE_CHAT_VIDEO_RECOVERY"] == "1", "Explicit long-VIDEO recovery acceptance only")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check", "--ui-test-diagnostics"]
        app.launch()
        let ui = ChatUI(app: app); ui.openChat()
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "isEnabled == true"), object: app.buttons["chat.attach"])], timeout: 60)
        ui.mode("video"); ui.videoLength("20")
        XCTAssertEqual(app.buttons["chat.videoDuration"].label, "Video length, 20 s")
        ui.type("A slow synthetic long scene for recovery")
        let before = ui.videoPlayers
        app.buttons["chat.send"].tap()
        let statuses = ui.follow(timeout: 900)
        XCTAssertTrue(statuses.contains { $0.hasPrefix("Generating segment") && $0.contains("of 10") }, statuses.joined(separator: " | "))
        XCTAssertTrue(app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 60))
        XCTAssertEqual(ui.videoPlayers, before + 1, "exactly one new artifact")
        let played = ui.lastPlayerDiagnostic()
        XCTAssertEqual(played.seconds, 20, accuracy: 0.5); XCTAssertGreaterThanOrEqual(played.audioTracks, 1)
        ui.screenshot(self, "test-host-long-video-recovered")
    }

    /// Host started with --chat-legacy: olive-chat/1 without the mode_options/1 extension.
    @MainActor func testOlderComputerVideoFallback() throws {
        try XCTSkipUnless(enabled && ProcessInfo.processInfo.environment["OLIVE_CHAT_LEGACY_HOST"] == "1", "Explicit older-computer acceptance only")
        continueAfterFailure = false
        let ui = launch()
        ui.mode("video")
        XCTAssertFalse(ui.app.buttons["chat.videoDuration"].waitForExistence(timeout: 5), "no Duration control for an older computer")
        ui.attach("photos")
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        let notice = ui.app.staticTexts["chat.composerNotice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 5)); XCTAssertTrue(notice.label.contains("VIDEO currently supports text prompts only"), notice.label)
        XCTAssertFalse(ui.app.buttons["chat.send"].isEnabled)
        ui.screenshot(self, "test-host-legacy-video-image-rejected")
        ui.app.buttons["chat.attachment.remove"].firstMatch.tap()
        for mode in ["fast", "normal", "max"] {
            ui.mode(mode); ui.type("Reply with exactly: \(mode)-mobile-ready"); ui.send()
            XCTAssertTrue(ui.app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "\(mode)-mobile-ready")).firstMatch.waitForExistence(timeout: 20), mode)
        }
        ui.mode("video"); ui.type("A short calm synthetic scene"); ui.send(timeout: 120)
        XCTAssertTrue(ui.app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 90))
        // Stays connected: no reconnect loop after the extension was declined.
        var seen = Set<String>()
        for _ in 0..<15 { seen.insert(ui.app.staticTexts["chat.draftStatus"].label); sleep(1) }
        NSLog("OLIVE-DIAG legacy header statuses %@", seen.sorted().joined(separator: " | "))
        XCTAssertFalse(seen.contains { $0.localizedCaseInsensitiveContains("connecting") || $0.localizedCaseInsensitiveContains("offline") }, seen.sorted().joined(separator: " | "))
        ui.screenshot(self, "test-host-legacy-text-modes")
    }
}

/// OPT-IN physical acceptance of OLIVE VIDEO length and image-to-video against the user's REAL paired
/// computer, using the normal app profile and its existing pairing. Each test is gated on its own
/// OLIVE_CHAT_REAL_VIDEO_STEP value and runs at most ONE real GPU generation. Images are generated by
/// the test (never the person's photos). Refuses to run if the composer holds unsent user text.
final class ChatRealVideoTests: XCTestCase {
    private func gate(_ step: String) throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_CHAT_REAL_VIDEO_STEP"] == step, "Explicit real-computer VIDEO step only")
        continueAfterFailure = false
    }
    private var seconds: String { ProcessInfo.processInfo.environment["OLIVE_CHAT_REAL_VIDEO_SECONDS"] ?? "20" }
    private static let prompts = ["Generate a 13 second video of gentle waves.",
                                  "Generate a cinematic scene of clouds moving over a futuristic city.",
                                  "Animate the clouds slowly and move the subject gradually across the scene.",
                                  "Generate a calm scene of fog drifting across a quiet harbour.",
                                  "Reply with exactly: normal-after-video-stop"]

    @MainActor private func launch() throws -> ChatUI {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-test-real-desktop", "--ui-test-synthetic-pickers", "--ui-test-diagnostics"]
        app.launch()
        let ui = ChatUI(app: app); ui.openChat()
        XCTAssertTrue(ui.composer.waitForExistence(timeout: 30))
        // Only this test's own leftovers (from an interrupted run) are cleared; anything else is the person's.
        let existing = (ui.composer.value as? String) ?? ""
        let ours = Self.prompts.contains { !existing.isEmpty && $0.hasPrefix(existing.replacingOccurrences(of: "...", with: "").replacingOccurrences(of: "…", with: "")) }
        try XCTSkipUnless(existing.isEmpty || existing == "Message OLIVE" || ours, "The composer holds unsent text; not touching the user's draft")
        let removes = app.buttons.matching(identifier: "chat.attachment.remove").allElementsBoundByIndex
        try XCTSkipUnless(removes.allSatisfy { $0.label.hasPrefix("Remove Synthetic") }, "The draft holds attachments; not touching them")
        if ours { ui.clearComposer() }
        while app.buttons["chat.attachment.remove"].firstMatch.exists { app.buttons["chat.attachment.remove"].firstMatch.tap(); sleep(1) }
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "isEnabled == true"), object: app.buttons["chat.attach"])], timeout: 120)
        XCTAssertTrue(app.buttons["chat.attach"].isEnabled, "olive-chat/1 not negotiated with the real computer")
        return ui
    }

    /// Negotiation, Duration UI and image rules against the real computer. Sends nothing.
    @MainActor func testCapabilitiesDurationAndImageRules() throws {
        try gate("capabilities")
        let ui = try launch(), app = ui.app
        ui.mode("video")
        let length = app.buttons["chat.videoDuration"]
        XCTAssertTrue(length.waitForExistence(timeout: 20), "the computer did not offer configurable VIDEO length")
        let advertised = (length.value as? String) ?? ""
        NSLog("OLIVE-DIAG real VIDEO capability %@", advertised)
        for expected in ["extensions=mode_options/1", "t2v=true", "i2v=true", "audio=true", "max_images=1", "image_max=1", "configurable=true"] {
            XCTAssertTrue(advertised.contains(expected), expected)
        }
        XCTAssertTrue(length.label.hasPrefix("Video length, Auto"), length.label)
        ui.screenshot(self, "real-video-duration-auto")
        length.tap()
        for option in ["auto", "2", "5", "10", "20", "30", "60"] {
            let row = app.buttons["chat.videoDuration.option." + option]
            for _ in 0..<4 where !(row.waitForExistence(timeout: 2) && row.isHittable) { app.collectionViews.firstMatch.swipeUp() }
            XCTAssertTrue(row.exists, option)
        }
        let custom = app.textFields["chat.videoDuration.custom"]
        for _ in 0..<4 where !(custom.waitForExistence(timeout: 2) && custom.isHittable) { app.collectionViews.firstMatch.swipeUp() }
        XCTAssertTrue(custom.exists)
        ui.screenshot(self, "real-video-duration-sheet")
        app.buttons["chat.videoDuration.done"].tap()
        ui.type("Generate a 13 second video of gentle waves.")
        XCTAssertEqual(length.label, "Video length, Auto · 13 s")
        let plan = app.descendants(matching: .any)["chat.videoPlan"]
        XCTAssertTrue(plan.waitForExistence(timeout: 5)); NSLog("OLIVE-DIAG real plan %@", plan.label)
        ui.screenshot(self, "real-video-auto-13")
        ui.clearComposer()
        ui.attach("photos")
        XCTAssertTrue(app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        XCTAssertTrue(plan.waitForExistence(timeout: 5)); XCTAssertTrue(plan.label.contains("Image → Video"), plan.label)
        XCTAssertFalse(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'supports text prompts only'")).firstMatch.exists)
        ui.screenshot(self, "real-video-image-to-video")
        ui.attach("camera")  // A different generated image (identical bytes would be deduplicated).
        let notice = app.staticTexts["chat.composerNotice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 15)); XCTAssertTrue(notice.label.contains("accepts one starting image"), notice.label)
        XCTAssertFalse(app.buttons["chat.send"].isEnabled)
        ui.screenshot(self, "real-video-second-image-rejected")
        while app.buttons["chat.attachment.remove"].firstMatch.exists { app.buttons["chat.attachment.remove"].firstMatch.tap(); sleep(1) }
        ui.mode("normal")  // Leave the conversation as it was found.
    }

    /// ONE real text-to-video generation at the chosen length (default 20 s).
    @MainActor func testTextToVideoAtChosenLength() throws {
        try gate("t2v")
        let ui = try launch(), app = ui.app
        ui.mode("video"); ui.videoLength(seconds)
        XCTAssertEqual(app.buttons["chat.videoDuration"].label, "Video length, \(seconds) s")
        ui.type("Generate a cinematic scene of clouds moving over a futuristic city.")
        NSLog("OLIVE-DIAG real plan %@", app.descendants(matching: .any)["chat.videoPlan"].label)
        let before = ui.videoPlayers
        app.buttons["chat.send"].tap()
        let statuses = ui.follow(timeout: 5400)
        verifyResult(ui, statuses: statuses, before: before, name: "real-t2v")
    }

    /// ONE real image-to-video generation from a generated image; a second image is refused first.
    @MainActor func testImageToVideoAtChosenLength() throws {
        try gate("i2v")
        let ui = try launch(), app = ui.app
        ui.mode("video"); ui.videoLength(seconds)
        ui.attach("photos")
        XCTAssertTrue(app.descendants(matching: .any)["chat.attachment.photo"].waitForExistence(timeout: 15))
        ui.attach("camera")  // A different generated image (identical bytes would be deduplicated).
        let notice = app.staticTexts["chat.composerNotice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 15)); XCTAssertTrue(notice.label.contains("accepts one starting image"), notice.label)
        XCTAssertFalse(app.buttons["chat.send"].isEnabled, "a second image is refused before sending")
        app.descendants(matching: .any)["chat.attachment.camera"].buttons["chat.attachment.remove"].tap(); sleep(1)
        XCTAssertTrue(app.descendants(matching: .any)["chat.attachment.photo"].exists, "the starting image stays")
        XCTAssertEqual(app.buttons.matching(identifier: "chat.attachment.remove").count, 1)
        ui.type("Animate the clouds slowly and move the subject gradually across the scene.")
        let plan = app.descendants(matching: .any)["chat.videoPlan"]
        XCTAssertTrue(plan.label.contains("Image → Video"), plan.label); NSLog("OLIVE-DIAG real plan %@", plan.label)
        ui.screenshot(self, "real-i2v-ready")
        let before = ui.videoPlayers
        app.buttons["chat.send"].tap()
        let statuses = ui.follow(timeout: 5400)
        verifyResult(ui, statuses: statuses, before: before, name: "real-i2v")
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'from your image'")).firstMatch.exists,
                      "the computer reports it animated the image")
    }

    @MainActor private func verifyResult(_ ui: ChatUI, statuses: [String], before: Int, name: String) {
        let app = ui.app
        let segments = statuses.filter { $0.hasPrefix("Generating segment") }
        NSLog("OLIVE-DIAG %@ segment statuses %@", name, segments.joined(separator: " | "))
        XCTAssertFalse(segments.isEmpty, statuses.joined(separator: " | "))
        XCTAssertTrue(app.descendants(matching: .any)["chat.video.player"].firstMatch.waitForExistence(timeout: 120), ui.lastStatus())
        XCTAssertEqual(ui.videoPlayers, before + 1, "exactly one new artifact")
        let target = Double(seconds) ?? 20
        let played = ui.lastPlayerDiagnostic()
        XCTAssertEqual(played.seconds, target, accuracy: max(1.0, target * 0.1)); XCTAssertGreaterThanOrEqual(played.audioTracks, 1)
        ui.screenshot(self, name + "-result")
        ui.mode("normal")
    }

    /// No generation: plays the newest downloaded video, opens the Share Sheet, then relaunches the app
    /// and checks the same video is still there (downloaded once, never requested again).
    @MainActor func testLatestVideoPlaysSharesAndSurvivesRelaunch() throws {
        try gate("playback")
        var ui = try launch()
        let app = ui.app
        let player = app.descendants(matching: .any).matching(identifier: "chat.video.player").allElementsBoundByIndex.last!
        XCTAssertTrue(player.waitForExistence(timeout: 30))
        let players = ui.videoPlayers
        let before = ui.playerDiagnostic()
        XCTAssertGreaterThan(before.seconds, 0)
        player.tap(); sleep(1)
        let control = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Play' OR label == 'Pause'")).firstMatch
        if !control.exists { player.tap(); sleep(1) }
        XCTAssertTrue(control.waitForExistence(timeout: 5), "AVKit playback controls")
        if control.label == "Play" { control.tap() }
        sleep(6)
        let playing = ui.playerDiagnostic()
        NSLog("OLIVE-DIAG playback before=%.1f after=%.1f rate=%.1f duration=%.3f audio=%d session=%@",
              before.position, playing.position, playing.rate, playing.seconds, playing.audioTracks, playing.session)
        XCTAssertGreaterThan(playing.position, before.position + 2, "AVPlayer advanced")
        XCTAssertEqual(playing.session, "AVAudioSessionCategoryPlayback", "video sound is audible with the Ring/Silent switch on")
        ui.screenshot(self, "real-video-playing")
        player.tap(); sleep(1)
        let pause = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Pause'")).firstMatch
        if pause.waitForExistence(timeout: 3) { pause.tap() }
        let share = app.buttons.matching(identifier: "chat.artifact.share").allElementsBoundByIndex.last!
        share.tap()
        XCTAssertTrue(app.otherElements["ActivityListView"].waitForExistence(timeout: 10), "Share Sheet did not open")
        ui.screenshot(self, "real-video-share")
        let close = app.buttons["Close"].firstMatch
        if close.exists { close.tap() } else { app.swipeDown() }
        sleep(1)
        app.terminate()
        ui = try launch()
        let again = ui.app.descendants(matching: .any).matching(identifier: "chat.video.player").allElementsBoundByIndex.last!
        XCTAssertTrue(again.waitForExistence(timeout: 30))
        let relaunched = ui.playerDiagnostic()
        NSLog("OLIVE-DIAG relaunch players=%d (was %d) duration=%.3f audio=%d", ui.videoPlayers, players, relaunched.seconds, relaunched.audioTracks)
        XCTAssertEqual(ui.videoPlayers, players); XCTAssertEqual(relaunched.seconds, before.seconds, accuracy: 0.01)
        XCTAssertFalse(ui.app.buttons["chat.stop"].exists, "nothing was sent again")
        ui.screenshot(self, "real-video-after-relaunch")
    }

    /// Stop during a real VIDEO once segment progress is shown, then a NORMAL request works.
    @MainActor func testStopDuringVideoThenNormal() throws {
        try gate("stop")
        let ui = try launch(), app = ui.app
        ui.mode("video"); ui.videoLength(seconds)
        ui.type("Generate a calm scene of fog drifting across a quiet harbour.")
        let before = ui.videoPlayers
        app.buttons["chat.send"].tap()
        let stop = app.buttons["chat.stop"]
        XCTAssertTrue(stop.waitForExistence(timeout: 30))
        let started = Date()
        var status = ""
        while Date().timeIntervalSince(started) < 1800 {
            status = ui.lastStatus()
            if status.hasPrefix("Generating segment 2") || status.hasPrefix("Generating segment 3") { break }
            sleep(2)
        }
        NSLog("OLIVE-DIAG stop pressed after %.0fs at status=%@", Date().timeIntervalSince(started), status)
        XCTAssertTrue(status.hasPrefix("Generating segment"), status)
        ui.screenshot(self, "real-video-before-stop")
        stop.tap()
        XCTAssertTrue(app.staticTexts["Generation stopped."].waitForExistence(timeout: 120), ui.lastStatus())
        ui.screenshot(self, "real-video-stopped")
        sleep(60)  // A late artifact would appear here.
        XCTAssertEqual(ui.videoPlayers, before, "no late artifact after Stop")
        XCTAssertEqual(ui.lastStatus(), "Generation stopped.")
        ui.mode("normal"); ui.type("Reply with exactly: normal-after-video-stop")
        let normal = Date()
        ui.send(timeout: 600)
        NSLog("OLIVE-DIAG normal after stop seconds=%.1f status=%@", Date().timeIntervalSince(normal), ui.lastStatus())
        XCTAssertGreaterThanOrEqual(app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'normal-after-video-stop'")).count, 2)
        ui.screenshot(self, "real-normal-after-stop")
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
