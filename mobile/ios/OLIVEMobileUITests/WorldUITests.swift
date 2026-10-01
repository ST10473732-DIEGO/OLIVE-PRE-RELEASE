import XCTest

/// OPT-IN physical acceptance of OLIVE Connect World against the Mac TEST HOST
/// (`tests/fixtures/draw_phone_test_host.py --chat --world`), with Direct forced off.
/// Uses the separate acceptance identity (--c92-pairing-check), never the user's pairing.
/// Run once WITHOUT --olive-world-force first (same Wi-Fi) so the computer provisions the route.
/// This verifies the relay path on one LAN; it is not a cellular/internet acceptance.
final class WorldTestHostTests: XCTestCase {
    private var enabled: Bool { ProcessInfo.processInfo.environment["OLIVE_WORLD_TEST_HOST"] == "1" }

    private func launch(forceWorld: Bool) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--c92-pairing-check", "--olive-world-test-lan"] + (forceWorld ? ["--olive-world-force"] : [])
        app.launch()
        app.tabBars.buttons["Devices"].tap()
        return app
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
    }

    /// Step 2 (Direct forced off): the same pair connects through the relay.
    @MainActor func testConnectedThroughWorld() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        let app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90), "World did not connect")
    }

    /// Step 3: force-quit and relaunch; the Keychain route persists and World returns without re-pairing.
    @MainActor func testRelaunchReconnectsThroughWorld() throws {
        try XCTSkipUnless(enabled, "Explicit World test-host acceptance only")
        var app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90))
        app.terminate()
        app = launch(forceWorld: true)
        XCTAssertTrue(app.staticTexts["Connected · World"].waitForExistence(timeout: 90), "World did not return after relaunch")
    }
}
