import Foundation
import Testing

@testable import GhostChef

/// IOS-03.2 acceptance: the state machine against `MockAPI` and a test clock.
@MainActor
@Suite("CookSession")
struct CookSessionTests {
    let recipe: Recipe
    let api: MockAPI
    let clock = TestClock()
    let speech = FakeSpeech()
    let frames = FakeFrameSource()
    let session: CookSession

    init() throws {
        recipe = try FixtureRecipe.load()
        api = MockAPI(recipe: recipe)
        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("CookSessionTests-\(UUID().uuidString)")
        session = CookSession(
            api: api, frames: frames, speech: speech, clock: clock,
            cache: ImageCache(directory: cacheDir))
    }

    private func started() async -> CookSession {
        await session.start(recipe: recipe)
        #expect(session.lens.stepIdx == 1)
        return session
    }

    private func checkCalls() async -> Int {
        await api.calls.filter { if case .check = $0 { true } else { false } }.count
    }

    // MARK: Start

    @Test func startCachesMediaOpensSessionAndSpeaksStepOne() async throws {
        let s = await started()
        #expect(s.phase == .cooking)
        #expect(s.sessionID != nil)
        let card = try #require(s.lens.card)
        #expect(card.total == recipe.steps.count)
        let ref = try #require(card.refImage, "step 1 image should come from the cache")
        #expect(ref.fileURL.path.contains("CookSessionTests-"))
        #expect(s.prefetchReport?.downloaded == recipe.steps.count)
        #expect(speech.spoken.last == .init(text: "Step 1 of 6. Lay out bread. Two slices side by side, flat.", priority: .info))
    }

    // MARK: Acceptance

    @Test func fixThenRecheckPassThenAutoAdvanceAfterTwoSeconds() async throws {
        let s = await started()
        await api.enqueueCheck(
            .success(checkResponse(.fix, headline: "Edges left bare", fix: "Spread right to the crust", spoken: "Edges left bare, spread to the crust.")),
            .success(checkResponse(.pass, headline: "Looks right", spoken: "That looks right.")))

        s.send(.primary)
        #expect(s.lens.isChecking)
        await eventually("fix") { s.lens.isFix }
        guard case .fix(let card, let headline, let fix, let proactive) = s.lens else { return }
        #expect(card.idx == 1 && headline == "Edges left bare" && fix == "Spread right to the crust" && !proactive)
        #expect(speech.spoken.last == .init(text: "Edges left bare, spread to the crust.", priority: .result))

        s.send(.primary)  // re-check
        await eventually("pass") { s.lens.isPass }
        #expect(speech.chimes == 1)
        #expect(speech.spoken.last == .init(text: "That looks right.", priority: .result))

        await eventually("auto-advance timer armed") { clock.pendingCount == 1 }
        clock.advance(by: .milliseconds(1900))
        await settle()
        #expect(s.lens.isPass, "must not advance before 2 s")
        clock.advance(by: .milliseconds(100))
        await eventually("step 2") { s.lens.stepIdx == 2 }

        await eventually("step_change posted") { await api.postedEvents.contains { $0.kind == .stepChange } }
        let change = try #require(await api.postedEvents.first { $0.kind == .stepChange })
        #expect(change.payload == ["from_idx": .number(1), "to_idx": .number(2), "via": .string("auto")])
        #expect(change.stepID == recipe.steps[1].id)
        #expect(await checkCalls() == 2)
    }

    @Test func primaryDuringPassAdvancesImmediately() async throws {
        let s = await started()
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
        s.send(.primary, via: .pinch)
        #expect(s.lens.stepIdx == 2)
        // The cancelled auto-advance must not fire a second advance.
        clock.advance(by: .seconds(5))
        await settle()
        #expect(s.lens.stepIdx == 2)
        await eventually("event") { await api.postedEvents.count == 1 }
        #expect(await api.postedEvents.first?.payload["via"] == .string("pinch"))
    }

    @Test func slowCheckArrivingAfterNextIsIgnored() async throws {
        let s = await started()
        await api.setHoldChecks(true)
        await api.enqueueCheck(.success(checkResponse(.fix, headline: "Edges left bare", spoken: "stale fix")))
        s.send(.primary)
        await eventually("check in flight") { await api.heldCheckCount == 1 }

        s.send(.next)
        #expect(s.lens.stepIdx == 2)
        #expect(s.latestCheckRequestID == nil)
        await api.releaseChecks()
        await settle()

        #expect(s.lens.stepIdx == 2, "a stale verdict must not replace the new step")
        #expect(!speech.texts.contains("stale fix"))
    }

    @Test func twoRapidPrimaryInputsMakeOneCheck() async throws {
        let s = await started()
        await api.setHoldChecks(true)
        s.send(.primary)
        s.send(.primary)
        await eventually("check in flight") { await api.heldCheckCount == 1 }
        s.send(.primary)
        await settle()
        #expect(await checkCalls() == 1)
        await api.releaseChecks()
        await eventually("pass") { s.lens.isPass }
        #expect(await checkCalls() == 1)
    }

    @Test func unsureReturnsToStepAfterFourSeconds() async throws {
        let s = await started()
        await api.enqueueCheck(.success(checkResponse(.unsure, headline: "Can't tell", fix: "Look straight down at mat")))
        s.send(.primary)
        await eventually("unsure") { s.lens.isUnsure }
        #expect(s.lens == .unsure(headline: "Can't tell", hint: "Look straight down at mat"))
        // Empty `spoken` falls back to the lens's spoken form.
        #expect(speech.spoken.last == .init(text: "Can't tell. Look straight down at mat.", priority: .result))

        await eventually("timer") { clock.pendingCount == 1 }
        clock.advance(by: .milliseconds(3900))
        await settle()
        #expect(s.lens.isUnsure)
        clock.advance(by: .milliseconds(100))
        await eventually("back to step 1") { s.lens.stepIdx == 1 }
    }

    @Test func timeoutIsRetriedOnceThenShowsNotice() async throws {
        let s = await started()
        let timeout = APIError(status: 504, code: .modelTimeout, message: "slow", retryable: true)
        await api.enqueueCheck(.failure(timeout), .failure(timeout))
        s.send(.primary)

        await eventually("retry delay armed") { clock.pendingCount == 1 }
        #expect(await checkCalls() == 1)
        #expect(s.lens.isChecking, "no notice before the retry")
        clock.advance(by: .seconds(1))

        await eventually("notice") { s.lens.noticeText != nil }
        #expect(s.lens == .notice("Can't check right now"))
        #expect(await checkCalls() == 2)
        #expect(speech.spoken.last == .init(text: "Can't check right now", priority: .result))

        await eventually("notice timer") { clock.pendingCount == 1 }
        clock.advance(by: .seconds(3))
        await eventually("back to step") { s.lens.stepIdx == 1 }
    }

    @Test func retryThatSucceedsShowsTheVerdict() async throws {
        let s = await started()
        await api.enqueueCheck(
            .failure(APIError(status: 503, code: .modelUnavailable, message: "x", retryable: true)),
            .success(checkResponse(.pass, headline: "Looks right")))
        s.send(.primary)
        await eventually("retry delay") { clock.pendingCount == 1 }
        clock.advance(by: .seconds(1))
        await eventually("pass") { s.lens.isPass }
    }

    @Test func quotaErrorIsNotRetried() async throws {
        let s = await started()
        await api.enqueueCheck(.failure(APIError(status: 429, code: .quotaExhausted, message: "q", retryable: true)))
        s.send(.primary)
        await eventually("notice") { s.lens.noticeText != nil }
        #expect(s.lens == .notice("Can't check right now"))
        #expect(await checkCalls() == 1)
    }

    @Test func networkErrorShowsNoConnection() async throws {
        let s = await started()
        await api.enqueueCheck(.failure(.network(message: "offline", timedOut: false)))
        s.send(.primary)
        await eventually("notice") { s.lens.noticeText != nil }
        #expect(s.lens == .notice("No connection"))
        #expect(s.watchIndicator == .offline)
        #expect(await checkCalls() == 1)
    }

    @Test func missingFrameShowsCameraNotice() async throws {
        let s = await started()
        frames.frame = nil
        s.send(.primary)
        await eventually("notice") { s.lens.noticeText != nil }
        #expect(s.lens == .notice("Camera off"))
        #expect(await checkCalls() == 0)
    }

    @Test func finishingLastStepPostsSessionEndAndShowsDone() async throws {
        let s = await started()
        // One fix on step 1, then a pass; the rest skipped with Next.
        await api.enqueueCheck(.success(checkResponse(.fix, headline: "Edges left bare")), .success(checkResponse(.pass)))
        s.send(.primary)
        await eventually("fix") { s.lens.isFix }
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
        s.send(.primary)  // advance now
        for _ in 2..<recipe.steps.count { s.send(.next) }
        #expect(s.lens.stepIdx == recipe.steps.count)

        s.send(.next)
        #expect(s.isDone)
        await eventually("summary") { s.lens.doneSummary??.stepsTotal != nil }
        let sessionID = try #require(s.sessionID)
        let expected = try await api.session(id: sessionID).summary
        #expect(s.lens == .done(expected))
        #expect(expected?.fixesCaught == 1)
        #expect(expected?.stepsPassedFirstTry == 0)
        #expect(await api.postedEvents.contains { $0.kind == .sessionEnd })
        #expect(speech.texts.last?.hasPrefix("Done.") == true)

        // Inputs other than Restart do nothing on the Done screen.
        s.send(.previous)
        s.send(.primary)
        #expect(s.isDone)
    }

    @Test func autoAdvanceOnLastStepFinishes() async throws {
        let s = await started()
        for _ in 1..<recipe.steps.count { s.send(.next) }
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
        await eventually("timer") { clock.pendingCount == 1 }
        clock.advance(by: .seconds(2))
        await eventually("done") { s.isDone }
        await eventually("session_end") { await api.postedEvents.contains { $0.kind == .sessionEnd } }
    }

    // MARK: Navigation and other inputs

    @Test func navigationIsBoundsCheckedAndPostsTapEvents() async throws {
        let s = await started()
        s.send(.previous)
        #expect(s.lens.stepIdx == 1)
        s.send(.next)
        s.send(.next)
        s.send(.previous)
        #expect(s.lens.stepIdx == 2)
        await eventually("3 events") { await api.postedEvents.count == 3 }
        let vias = await api.postedEvents.map { $0.payload["via"] }
        #expect(vias == Array(repeating: .string("tap"), count: 3))
        let last = await api.postedEvents.last?.payload
        #expect(last?["from_idx"] == .number(3) && last?["to_idx"] == .number(2))
        #expect(speech.spoken.last == .init(text: "Step 2 of 6. Spread. Thin layer, right to every edge.", priority: .info))
    }

    @Test func dismissOnFixReturnsToStep() async throws {
        let s = await started()
        await api.enqueueCheck(.success(checkResponse(.fix, headline: "Edges left bare", fix: "Spread right to the crust")))
        s.send(.primary)
        await eventually("fix") { s.lens.isFix }
        s.send(.dismiss)
        #expect(s.lens.stepIdx == 1)
    }

    @Test func repeatInstructionSpeaksFullInstruction() async throws {
        let s = await started()
        s.send(.repeatInstruction)
        #expect(speech.spoken.last == .init(text: recipe.steps[0].instruction, priority: .result))
        #expect(s.lens.stepIdx == 1)
    }

    @Test func showMePostsEventAndDismissReturns() async throws {
        let s = await started()
        s.send(.showMe)
        guard case .showMe(let card) = s.lens else {
            Issue.record("expected showMe, got \(s.lens)")
            return
        }
        #expect(card.idx == 1)
        await eventually("show_me") { await api.postedEvents.contains { $0.kind == .showMe } }
        s.send(.dismiss)
        #expect(s.lens.stepIdx == 1)
    }

    @Test func restartOpensANewSessionAtStepOne() async throws {
        let s = await started()
        let first = s.sessionID
        for _ in 0..<recipe.steps.count { s.send(.next) }
        #expect(s.isDone)
        s.restart()
        await eventually("step 1 again") { s.lens.stepIdx == 1 && s.sessionID != nil && s.sessionID != first }
        #expect(s.phase == .cooking)
    }

    @Test func noSessionStillCooks() async throws {
        // POST /sessions failing must not block cooking: build an API whose createSession throws.
        struct NoSessionAPI: GhostChefAPI {
            let base: MockAPI
            func health() async throws -> Health { try await base.health() }
            func recipes(status: RecipeStatus?) async throws -> [RecipeSummary] { try await base.recipes(status: status) }
            func recipe(id: String) async throws -> Recipe { try await base.recipe(id: id) }
            func createSession(recipeID: String, deviceLabel: String?) async throws -> SessionCreated {
                throw APIError.network(message: "offline", timedOut: false)
            }
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
        let s = CookSession(
            api: NoSessionAPI(base: api), frames: frames, speech: speech, clock: clock,
            cache: ImageCache(directory: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)))
        await s.start(recipe: recipe)
        #expect(s.sessionID == nil)
        #expect(s.lens.stepIdx == 1)
        s.send(.next)
        #expect(s.lens.stepIdx == 2)
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
        await settle()
        #expect(await api.postedEvents.isEmpty)
    }

    @Test func fixtureMockMimicsFakeAI() async throws {
        let mimic = MockAPI(recipe: recipe, mimicFakeAI: true)
        let s = CookSession(
            api: mimic, frames: frames, speech: speech, clock: clock,
            cache: ImageCache(directory: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)))
        await s.start(recipe: recipe)
        s.send(.next)  // step 2 has the spread_misses_edges watch-for
        s.send(.primary)
        await eventually("fix") { s.lens.isFix }
        guard case .fix(_, let headline, let fix, _) = s.lens else { return }
        #expect(headline == "Edges left bare" && fix == "Spread right to the crust")
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
    }
}
