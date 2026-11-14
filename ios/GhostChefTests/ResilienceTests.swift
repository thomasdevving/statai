import Foundation
import Testing

@testable import GhostChef

// IOS-07: resilience rules, input robustness (07.5), demo start step (07.6), and the pieces that
// run without a device (switchable frames, backend reachability, the audio-only narrator).

// MARK: - Output mode and narration (07.1, 07.2)

@Suite("Output mode")
struct OutputModeTests {
    @Test func audioOnlyWhenForcedOrNoWorkingDisplayOnTheGlasses() {
        func mode(forced: Bool = false, glasses: Bool = false, display: Bool = true, failed: Bool = false, muted: Bool = false) -> LensOutputMode {
            LensOutputMode.resolve(forcedAudioOnly: forced, cookingOnGlasses: glasses, glassesHaveDisplay: display, displayFailed: failed, speechMuted: muted)
        }
        #expect(mode() == .normal)
        #expect(mode(forced: true) == .audioOnly)
        #expect(mode(glasses: true, display: false) == .audioOnly, "Gen 2 glasses")
        #expect(mode(glasses: true, failed: true) == .audioOnly)
        #expect(mode(glasses: false, display: false) == .normal, "the phone preview is the display")
        #expect(mode(muted: true) == .displayOnly)
        #expect(mode(glasses: true, display: false, muted: true) == .audioOnly, "never blind and mute")
    }
}

@Suite("Audio-only narration")
struct AudioOnlyNarrationTests {
    let card = StepCard(idx: 4, total: 6, title: "Add fillings", keyLine: "One even layer, edge to edge", refImage: nil, watching: .active)

    @Test func checkingIsAToneOnce() {
        #expect(AudioOnlyNarration.narration(from: .step(card), to: .checking(card), lastStepIdx: 4) == .checkingTone)
        #expect(AudioOnlyNarration.narration(from: .checking(card), to: .checking(card), lastStepIdx: 4) == nil)
    }

    @Test func backOnTheSameStepIsSaidButANewStepIsLeftToCookSession() {
        let back = AudioOnlyNarration.speak("Back to step 4. One even layer, edge to edge.")
        #expect(AudioOnlyNarration.narration(from: .fix(card, headline: "Filling piled up", fix: "", proactive: true), to: .step(card), lastStepIdx: 4) == back)
        #expect(AudioOnlyNarration.narration(from: .unsure(headline: "Can't tell", hint: ""), to: .step(card), lastStepIdx: 4) == back)
        #expect(AudioOnlyNarration.narration(from: .notice("No connection"), to: .step(card), lastStepIdx: 4) == back)
        #expect(AudioOnlyNarration.narration(from: .pass(headline: "Looks right"), to: .step(card), lastStepIdx: 3) == nil, "advanced: already announced")
        #expect(AudioOnlyNarration.narration(from: .step(card.with(watching: .paused)), to: .step(card), lastStepIdx: 4) == nil, "dot change")
        #expect(AudioOnlyNarration.narration(from: .talking(phase: .answering, caption: ""), to: .step(card), lastStepIdx: 4) == nil)
    }

    @Test func showMeAndTimerAreSpoken() {
        #expect(AudioOnlyNarration.narration(from: .step(card), to: .showMe(card), lastStepIdx: 4) == .speak("Here is how the chef did it."))
        #expect(AudioOnlyNarration.narration(from: .step(card), to: .timer(remainingS: 90, card), lastStepIdx: 4) == .speak("1 minute 30 seconds left."))
        #expect(AudioOnlyNarration.narration(from: .step(card), to: .pass(headline: "Looks right"), lastStepIdx: 4) == nil, "results are spoken by CookSession")
    }
}

// MARK: - Glasses drop-outs, servers, build label

@Suite("Resilience rules")
struct ResilienceRuleTests {
    @Test func glassesDropOutAndReturn() {
        #expect(GlassesConnectionWatch.event(from: .ready(displays: true), to: .disconnected("hinges closed")) == .disconnected("hinges closed"))
        #expect(GlassesConnectionWatch.event(from: .ready(displays: true), to: .noDevice) == .disconnected("no glasses"))
        #expect(GlassesConnectionWatch.event(from: .ready(displays: true), to: .connecting) == nil)
        #expect(GlassesConnectionWatch.event(from: .disconnected("x"), to: .ready(displays: true)) == .reconnected)
        #expect(GlassesConnectionWatch.event(from: .connecting, to: .ready(displays: false)) == .reconnected)
        #expect(GlassesConnectionWatch.event(from: .ready(displays: true), to: .ready(displays: true)) == nil)
    }

    @Test func savedServersDefaultsAndValidation() {
        #expect(SavedServer.defaults.map(\.name) == ["Production", "Laptop"])
        #expect(SavedServer.defaults[0].validURL?.absoluteString == "https://statai-production.up.railway.app")
        #expect(SavedServer(name: "x", url: "not a url").validURL == nil)
        #expect(SavedServer(name: "x", url: "ftp://host").validURL == nil)
        #expect(SavedServer(name: "x", url: " http://10.0.0.2:8000 ").validURL?.host() == "10.0.0.2")
    }

    @MainActor @Test func settingsSwitchServersAndRemember() throws {
        let defaults = try #require(UserDefaults(suiteName: "ResilienceTests-\(UUID().uuidString)"))
        let settings = Settings(defaults: defaults)
        #expect(settings.savedServers == SavedServer.defaults)
        settings.use(SavedServer.defaults[0])
        #expect(settings.baseURLString == "https://statai-production.up.railway.app")
        #expect(settings.currentServer?.name == "Production")
        settings.savedServers[1].url = "http://10.0.41.234:8000"
        settings.demoStartStep = 4
        let reread = Settings(defaults: defaults)
        #expect(reread.savedServers[1].url == "http://10.0.41.234:8000")
        #expect(reread.demoStartStep == 4)
    }

    @Test func buildLabelFallsBackWhenUnstamped() {
        #expect(BuildLabel.current(bundle: Bundle(for: BundleToken.self)).hasPrefix("dev build"))
    }
}

private final class BundleToken {}

// MARK: - Switchable frames (07.4)

@Suite("Switchable frame source")
struct SwitchableFrameSourceTests {
    final class Source: FrameSource, @unchecked Sendable {
        let name: String
        var started = 0
        var stopped = 0
        var failStart = false
        init(_ name: String) { self.name = name }
        var isAvailable: Bool { started > stopped }
        func start() async throws {
            if failStart { throw FrameSourceError.noCamera }
            started += 1
        }
        func stop() { stopped += 1 }
        func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? { Data(name.utf8) }
    }

    @Test func switchingStartsTheNewOneThenStopsTheOld() async throws {
        let glasses = Source("glasses")
        let phone = Source("phone")
        let switchable = SwitchableFrameSource(glasses, kind: .glasses)
        try await switchable.start()
        #expect(await switchable.latestJPEG(maxLongEdge: 512, quality: 0.6) == Data("glasses".utf8))
        try await switchable.switchTo(phone, kind: .phoneCamera)
        #expect(switchable.currentKind == .phoneCamera)
        #expect(phone.started == 1 && glasses.stopped == 1)
        #expect(await switchable.latestJPEG(maxLongEdge: 512, quality: 0.6) == Data("phone".utf8))
    }

    @Test func aFailedSwitchKeepsTheOldSource() async throws {
        let glasses = Source("glasses")
        let phone = Source("phone")
        phone.failStart = true
        let switchable = SwitchableFrameSource(glasses, kind: .glasses)
        await #expect(throws: FrameSourceError.self) { try await switchable.switchTo(phone, kind: .phoneCamera) }
        #expect(switchable.currentKind == .glasses && glasses.stopped == 0)
    }
}

// MARK: - Backend reachability (07.3)

/// Forwards to `MockAPI` but lets `/health` fail.
struct FlakyHealthAPI: GhostChefAPI {
    let base: MockAPI
    let down: Bool
    func health() async throws -> Health {
        if down { throw APIError.network(message: "Could not connect to the server.", timedOut: false) }
        return try await base.health()
    }
    func recipes(status: RecipeStatus?) async throws -> [RecipeSummary] { try await base.recipes(status: status) }
    func recipe(id: String) async throws -> Recipe { try await base.recipe(id: id) }
    func createSession(recipeID: String, deviceLabel: String?) async throws -> SessionCreated { try await base.createSession(recipeID: recipeID, deviceLabel: deviceLabel) }
    func postEvent(sessionID: String, kind: SessionEventKind, stepID: String?, requestID: String?, payload: [String: JSONValue]) async throws -> EventCreated {
        try await base.postEvent(sessionID: sessionID, kind: kind, stepID: stepID, requestID: requestID, payload: payload)
    }
    func session(id: String) async throws -> SessionDetail { try await base.session(id: id) }
    func check(frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?) async throws -> CheckResponse {
        try await base.check(frame: frame, stepID: stepID, requestID: requestID, sessionID: sessionID, capturedAt: capturedAt)
    }
    func watch(frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?) async throws -> WatchResponse {
        try await base.watch(frame: frame, stepID: stepID, requestID: requestID, sessionID: sessionID, capturedAt: capturedAt)
    }
    func liveToken(recipeID: String, sessionID: String?) async throws -> LiveTokenResponse { try await base.liveToken(recipeID: recipeID, sessionID: sessionID) }
    func createRecipe(title: String, chefName: String?, stepMarksS: [Double], consent: Bool) async throws -> RecipeUpload {
        try await base.createRecipe(title: title, chefName: chefName, stepMarksS: stepMarksS, consent: consent)
    }
    func processRecipe(id: String) async throws -> ProcessStarted { try await base.processRecipe(id: id) }
}

@MainActor
@Suite("Backend reachability")
struct BackendReachabilityTests {
    @Test func reportsReachableAndUnreachable() async throws {
        let base = MockAPI(recipe: try FixtureRecipe.load())
        let up = BackendReachability(api: FlakyHealthAPI(base: base, down: false), clock: TestClock())
        await up.checkOnce()
        #expect(up.state == .reachable(aiMode: "fixture"))
        let down = BackendReachability(api: FlakyHealthAPI(base: base, down: true), clock: TestClock())
        await down.checkOnce()
        #expect(down.isUnreachable)
    }
}

// MARK: - CookSession robustness (07.5) and start step (07.6)

@MainActor
@Suite("CookSession robustness")
struct CookSessionRobustnessTests {
    let recipe: Recipe
    let api: MockAPI
    let clock = TestClock()
    let speech = FakeSpeech()
    let session: CookSession

    init() throws {
        recipe = try FixtureRecipe.load()
        api = MockAPI(recipe: recipe)
        session = CookSession(
            api: api, frames: FakeFrameSource(), speech: speech, clock: clock,
            cache: ImageCache(directory: FileManager.default.temporaryDirectory.appendingPathComponent("Robust-\(UUID().uuidString)")))
    }

    private func checks() async -> Int { await api.calls.filter { if case .check = $0 { true } else { false } }.count }

    @Test func fiveRapidPrimariesMakeOneCheck() async throws {
        await session.start(recipe: recipe)
        await api.setHoldChecks(true)
        for _ in 0..<5 { session.send(.primary) }
        await eventually("one check in flight", timeout: .seconds(15)) { await api.heldCheckCount == 1 }
        await settle()
        #expect(await checks() == 1)
        #expect(session.lens.isChecking)
        await api.releaseChecks()
        await eventually("one verdict") { session.lens.isPass }
        #expect(await checks() == 1)
    }

    @Test func passAndNoticeInputsAndEveryTimedScreenReturnsToTheStep() async throws {
        await session.start(recipe: recipe)
        // Pass: primary advances now.
        await api.enqueueCheck(.success(checkResponse(.pass, headline: "Looks right")))
        session.send(.primary)
        await eventually("pass") { session.lens.isPass }
        session.send(.primary)
        #expect(session.lens.stepIdx == 2)

        // Pass left alone: auto-advance after 2 s.
        await api.enqueueCheck(.success(checkResponse(.pass)))
        session.send(.primary)
        await eventually("pass 2") { session.lens.isPass }
        await eventually("auto-advance timer armed") { clock.pendingCount > 0 }
        clock.advance(by: .seconds(2))
        await eventually("auto-advanced") { session.lens.stepIdx == 3 }

        // Unsure: back to the step after 4 s.
        await api.enqueueCheck(.success(checkResponse(.unsure, headline: "Can't tell", fix: "Look down")))
        session.send(.primary)
        await eventually("unsure") { session.lens.isUnsure }
        await eventually("unsure timer armed") { clock.pendingCount > 0 }
        clock.advance(by: .seconds(4))
        await eventually("back from unsure") { session.lens.stepIdx == 3 }

        // Notice: dismiss returns at once; left alone it returns after 3 s.
        await api.enqueueCheck(.failure(APIError(status: 429, code: .quotaExhausted, message: "busy", retryable: true)))
        session.send(.primary)
        await eventually("notice") { session.lens.noticeText == CookSession.Notice.cantCheck }
        session.send(.dismiss)
        #expect(session.lens.stepIdx == 3)
        await api.enqueueCheck(.failure(APIError(status: 429, code: .quotaExhausted, message: "busy", retryable: true)))
        session.send(.primary)
        await eventually("notice 2") { session.lens.noticeText != nil }
        await eventually("notice timer armed") { clock.pendingCount > 0 }
        clock.advance(by: .seconds(3))
        await eventually("back from notice") { session.lens.stepIdx == 3 }

        // Primary on a notice checks again.
        await api.enqueueCheck(.failure(APIError(status: 429, code: .quotaExhausted, message: "busy", retryable: true)), .success(checkResponse(.pass)))
        session.send(.primary)
        await eventually("notice 3") { session.lens.noticeText != nil }
        session.send(.primary)
        await eventually("pass after notice") { session.lens.isPass }
    }

    @Test func demoStartsAtTheChosenStepAndTellsTheMonitor() async throws {
        session.startStep = { 4 }
        await session.start(recipe: recipe)
        #expect(session.lens.stepIdx == 4)
        await eventually("step_change") { await api.postedEvents.contains { $0.kind == .stepChange } }
        let change = try #require(await api.postedEvents.first { $0.kind == .stepChange })
        #expect(change.payload["from_idx"] == .number(1) && change.payload["to_idx"] == .number(4))
        #expect(speech.texts.last?.hasPrefix("Step 4 of 6.") == true)
        // Restart lands on the same step with a new session.
        let first = session.sessionID
        session.restart()
        await eventually("restarted") { session.sessionID != nil && session.sessionID != first }
        #expect(session.lens.stepIdx == 4)
    }

    @Test func startStepIsClampedToTheRecipe() async {
        session.startStep = { 99 }
        await session.start(recipe: recipe)
        #expect(session.lens.stepIdx == recipe.steps.count)
    }

    @Test func audioOnlyNarratorSpeaksTheReturnAndTheCheckTone() async throws {
        var tones = 0
        let narrator = SpokenLens(session: session, speech: speech, tone: { tones += 1 }, isActive: { true })
        await session.start(recipe: recipe)
        narrator.start()
        await api.enqueueCheck(.success(checkResponse(.unsure, headline: "Can't tell", fix: "Look down")))
        await api.setHoldChecks(true)  // a real check takes ~1 s; keep "Checking" on screen like it
        session.send(.primary)
        // Generous timeouts: a parallel AVFoundation test can stall the main thread for seconds.
        await eventually("tone", timeout: .seconds(15)) { tones == 1 }
        await eventually("check held", timeout: .seconds(15)) { await api.heldCheckCount == 1 }
        await api.releaseChecks()
        await eventually("unsure", timeout: .seconds(15)) { session.lens.isUnsure }
        await eventually("unsure timer armed", timeout: .seconds(15)) { clock.pendingCount > 0 }
        clock.advance(by: .seconds(4))
        await eventually("back", timeout: .seconds(15)) { speech.texts.contains { $0.hasPrefix("Back to step 1.") } }
        narrator.stop()
    }
}
