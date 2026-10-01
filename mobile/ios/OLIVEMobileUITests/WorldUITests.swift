import XCTest

/// TEST_RUNNER_OLIVE_WORLD_FORCE=1: the other test-host acceptance classes (Chat, Notes) launch the
/// DEBUG app with Direct forced off, so the same steps run through the Mac test host's World relay.
enum WorldLaunch {
    static var arguments: [String] {
        ProcessInfo.processInfo.environment["OLIVE_WORLD_FORCE"] == "1" ? ["--olive-world-test-lan", "--olive-world-force"] : []
    }
}

/// OPT-IN physical acceptance of OLIVE Connect World against the Mac TEST HOST
/// (`tests/fixtures/draw_phone_test_host.py --chat --world`), with Direct forced off.
/// Uses the separate acceptance identity (--c92-pairing-check), never the user's pairing.
/// Run once WITHOUT --olive-world-force first (same Wi-Fi) so the computer provisions the route.
/// This verifies the relay path on one LAN; it is not a cellular/internet acceptance.
final class WorldTestHostTests: XCTestCase {
    private var enabled: Bool { ProcessInfo.processInfo.environment["OLIVE_WORLD_TEST_HOST"] == "1" }

    @MainActor private func launch(forceWorld: Bool) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check", "--olive-world-test-lan"] + (forceWorld ? ["--olive-world-force"] : [])
        app.launch()
        app.tabBars.buttons["Devices"].tap()
        return app
    }

    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        XCTAssertEqual(app.state, .runningForeground)   // OLIVE only.
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }

    /// No route id (32 hex) or route secret / credential (64 hex) is ever shown.
    @MainActor private func assertNoSecretsShown(_ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) {
        let hex = try! NSRegularExpression(pattern: "[0-9a-fA-F]{32,}")
        for element in app.descendants(matching: .any).allElementsBoundByIndex.prefix(400) {
            for text in [element.label, element.value as? String ?? ""] where !text.isEmpty {
                let range = NSRange(text.startIndex..., in: text)
                XCTAssertNil(hex.firstMatch(in: text, range: range), "secret-like value shown: \(text.count) chars", file: file, line: line)
            }
        }
    }

    /// Step 1 (same Wi-Fi, Direct allowed): the computer provisions World for this pair.
    @MainActor func testProvisionOverDirect() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        let app = launch(forceWorld: false)
        XCTAssertTrue(app.staticTexts["Connected · Direct"].waitForExistence(timeout: 60), "not connected Direct")
        app.buttons["Permissions & details"].tap()
        let world = app.descendants(matching: .any)["devices.world"]
        let ready = NSPredicate(format: "value BEGINSWITH %@ OR label CONTAINS %@", "Ready", "Ready")
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: ready, object: world)], timeout: 30), .completed,
                       "World route was not provisioned")
        capture(app, "world-direct-provisioned")
        assertNoSecretsShown(app)
    }

    /// Step 2 (Direct forced off): the same pair connects through the relay.
    @MainActor func testConnectedThroughWorld() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        let app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90), "World did not connect")
        capture(app, "world-connected")
    }

    /// Step 3: force-quit and relaunch; the Keychain route persists and World returns without re-pairing.
    @MainActor func testRelaunchReconnectsThroughWorld() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        var app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90))
        app.terminate()
        app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90), "World did not return after relaunch")
        capture(app, "world-after-relaunch")
    }

    /// Diagnostics only: logs each change of the app's connection diagnostic line (states and
    /// failure codes, never content or keys) for OLIVE_WORLD_TRACE_SECONDS while the Mac drives
    /// Direct/World changes from the test host.
    @MainActor func testTracePathChanges() throws {
        let seconds = Double(ProcessInfo.processInfo.environment["OLIVE_WORLD_TRACE_SECONDS"] ?? "") ?? 0
        try XCTSkipUnless(enabled && seconds > 0, "Explicit World trace only")
        let app = launch(forceWorld: false)
        app.tabBars.buttons["Home"].tap()
        app.buttons["settings.open"].tap()
        let advanced = app.buttons["Advanced connection diagnostics"].firstMatch
        for _ in 0..<4 where !(advanced.exists && advanced.isHittable) { app.swipeUp() }
        advanced.tap()
        let world = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "World: ")).firstMatch
        XCTAssertTrue(world.waitForExistence(timeout: 10))
        let start = Date()
        var last = ""
        while Date().timeIntervalSince(start) < seconds {
            let lines = app.staticTexts.allElementsBoundByIndex.map(\.label)
                .filter { $0.hasPrefix("World: ") || $0.contains("tcp_tls") || $0.hasPrefix("authenticated") || $0.hasPrefix("discovery")
                          || $0.hasPrefix("inference") || $0.hasPrefix("identity") || $0.hasPrefix("connect:") }
            let now = lines.joined(separator: " | ")
            if now != last { NSLog("OLIVE-DIAG t=%.1f %@", Date().timeIntervalSince(start), now); last = now }
            usleep(250_000)
        }
    }

    /// Host started with --world-legacy (an OLIVE computer from before Connect World): Direct works,
    /// World reads "Not supported by this computer", and the connection stays up (no reconnect loop).
    @MainActor func testOlderComputerStaysDirect() throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_WORLD_LEGACY_HOST"] == "1", "Explicit older-computer acceptance only")
        let app = launch(forceWorld: false)
        XCTAssertTrue(app.staticTexts["Connected · Direct"].waitForExistence(timeout: 60), "not connected Direct")
        app.buttons["Permissions & details"].tap()
        let world = app.descendants(matching: .any)["devices.world"]
        let unsupported = NSPredicate(format: "label CONTAINS %@", "Not supported by this computer")
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: unsupported, object: world)], timeout: 30), .completed, world.label)
        var seen = Set<String>()
        for _ in 0..<30 {
            seen.insert(app.staticTexts["Connected · Direct"].exists ? "Connected · Direct" : "other")
            sleep(1)
        }
        XCTAssertEqual(seen, ["Connected · Direct"], "the connection must not cycle")
        capture(app, "world-older-computer")
        app.tabBars.buttons["Home"].tap()
        app.buttons["settings.open"].tap()
        let status = app.descendants(matching: .any)["settings.worldStatus"]
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertEqual(status.value as? String, "Not supported by this computer")
        capture(app, "world-older-computer-settings")
        app.buttons["settings.done"].tap()
    }

    /// Settings › OLIVE Connect World and the Devices details through World: states only, never a route or key.
    @MainActor func testSettingsAndDetailsShowStatesOnly() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        let app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90))
        app.buttons["Permissions & details"].tap()
        let world = app.descendants(matching: .any)["devices.world"]
        XCTAssertTrue(world.waitForExistence(timeout: 10))
        XCTAssertTrue(world.label.contains("Connected · World") || (world.value as? String ?? "").contains("Connected · World"), world.label)
        capture(app, "world-device-details")
        assertNoSecretsShown(app)
        app.tabBars.buttons["Home"].tap()
        app.buttons["settings.open"].tap()
        let toggle = app.switches["settings.world"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 10))
        XCTAssertEqual(toggle.value as? String, "1", "World is On by default once provisioned")
        let status = app.descendants(matching: .any)["settings.worldStatus"]
        XCTAssertEqual(status.value as? String, "Connected · World")
        capture(app, "world-settings-on")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "Off"), object: status)], timeout: 10), .completed)
        capture(app, "world-settings-off")
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        XCTAssertEqual(XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value != %@", "Off"), object: status)], timeout: 10), .completed)
        let advanced = app.buttons["Advanced connection diagnostics"].firstMatch
        for _ in 0..<4 where !(advanced.exists && advanced.isHittable) { app.swipeUp() }
        advanced.tap()
        let diagnostics = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "World: ")).firstMatch
        XCTAssertTrue(diagnostics.waitForExistence(timeout: 10))
        XCTAssertEqual(diagnostics.label, "World: supported · provisioned · path World")
        capture(app, "world-settings-diagnostics")
        assertNoSecretsShown(app)
        app.buttons["settings.done"].tap()
    }
}
