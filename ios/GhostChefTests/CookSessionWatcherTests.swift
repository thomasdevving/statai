import Foundation
import Testing

@testable import GhostChef

/// IOS-04.2 pause conditions and IOS-04.3 warning behaviour, through `CookSession`.
/// Fixture: step 1 watches for `nori_short_edge_near`, step 2 has no watch-fors.
@MainActor
@Suite("CookSession watcher")
struct CookSessionWatcherTests {
    final class ConfigBox { var value = WatcherConfig() }

    let recipe: Recipe
    let api: MockAPI
    let clock = TestClock()
    let speech = FakeSpeech()
    let frames = FakeFrameSource()
    let log = WatchLog()
    let config = ConfigBox()
    let session: CookSession
    let mistake = "nori_short_edge_near"

    init() throws {
        recipe = try FixtureRecipe.load()
        api = MockAPI(recipe: recipe)
        let cacheDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("CookSessionWatcherTests-\(UUID().uuidString)")
        let config = config
        session = CookSession(
            api: api, frames: frames, speech: speech, clock: clock, cache: ImageCache(directory: cacheDir),
            watchConfig: { config.value }, watchLog: log)
    }

    private func watchCalls() async -> Int { await api.watchCallCount }

    private func events(_ kind: SessionEventKind) async -> [MockAPI.PostedEvent] {
        await api.postedEvents.filter { $0.kind == kind }
    }

    /// Step 1 showing, first watch answered, loop sleeping out the interval.
    private func started() async -> CookSession {
        await session.start(recipe: recipe)
        #expect(session.lens.stepIdx == 1)
        await eventually("first watch") { await watchCalls() == 1 }
        await idle()
        return session
    }

    /// The watcher is between calls (sleeping its interval or waiting for the gate).
    private func idle() async {
        await eventually("watcher idle") { !session.watcher.isCallInFlight }
        await settle()
    }

    /// Next tick: advance one interval and wait for the call to be answered.
    private func tick() async {
        let before = await watchCalls()
        await eventually("interval timer") { clock.pendingCount >= 1 }
        clock.advance(by: .milliseconds(2500))
        await eventually("watch call") { await watchCalls() == before + 1 }
        await idle()
    }

    /// Two matching warns at 0.9: the warning shows.
    private func raiseWarning(_ s: CookSession) async {
        await api.enqueueWatch(
            .success(watchResponse(.warn, mistake, headline: "Nori turned", fix: "Long edge toward you", spoken: "Turn the nori.")),
            .success(watchResponse(.warn, mistake, headline: "Nori turned", fix: "Long edge toward you", spoken: "Turn the nori.")))
        await tick()
        #expect(!s.lens.isFix)
        await tick()
        await eventually("warning") { s.lens.isFix }
    }

    // MARK: Indicator

    @Test func watchingDotFollowsTheWatcher() async throws {
        let s = await started()
        #expect(s.watchIndicator == .active)
        #expect(s.lens.card?.watching == .active)
        s.setAppActive(false)
        #expect(s.lens.card?.watching == .paused)
        s.setAppActive(true)
        #expect(s.lens.card?.watching == .active)
    }

    @Test func stepWithoutWatchForsShowsDotOffAndMakesNoCalls() async throws {
        let s = await started()
        s.send(.next)
        #expect(s.lens.stepIdx == 2)
        #expect(s.watchGate == .off)
        #expect(s.lens.card?.watching == .off)
        clock.advance(by: .seconds(30))
        await settle()
        #expect(await watchCalls() == 1)
        s.send(.previous)
        await eventually("watching again on step 1") { await watchCalls() == 2 }
        #expect(s.lens.card?.watching == .active)
    }

    // MARK: Pause conditions

    /// Pauses, lets more than an interval pass (staying under every screen timer), checks nothing
    /// was sent, then resumes and expects a call.
    private func expectPause(
        _ what: String, _ s: CookSession, advance: Duration = .milliseconds(2600),
        pause: () async -> Void, resume: () async -> Void
    ) async {
        let before = await watchCalls()
        await pause()
        #expect(s.watchGate == .paused, "\(what): gate")
        clock.advance(by: advance)
        await settle()
        #expect(await watchCalls() == before, "\(what): no call while paused")
        await resume()
        #expect(s.watchGate != .paused, "\(what): gate open again")
        await eventually("\(what): resumes") { await watchCalls() > before }
        await idle()
    }

    @Test func pausedWhileNotOnTheStepCard() async throws {
        let s = await started()
        await expectPause("show me", s) { s.send(.showMe) } resume: { s.send(.dismiss) }
        await expectPause("unsure", s, advance: .seconds(3)) {
            await api.enqueueCheck(.success(checkResponse(.unsure, headline: "Can't tell")))
            s.send(.primary)
            await eventually("unsure") { s.lens.isUnsure }
        } resume: {
            clock.advance(by: .seconds(1))  // 4 s: back to the step
            await eventually("step") { s.lens.stepIdx == 1 }
        }
        await expectPause("fix", s) {
            await api.enqueueCheck(.success(checkResponse(.fix, headline: "Too much rice")))
            s.send(.primary)
            await eventually("fix") { s.lens.isFix }
        } resume: { s.send(.dismiss) }
        await expectPause("notice", s, advance: .milliseconds(2900)) {
            await api.enqueueCheck(.failure(.network(message: "x", timedOut: false)))
            s.send(.primary)
            await eventually("notice") { s.lens.noticeText != nil }
        } resume: {
            clock.advance(by: .milliseconds(100))
            await eventually("step") { s.lens.stepIdx == 1 }
        }
    }

    @Test func pausedWhileACheckIsInFlightAndOnPass() async throws {
        let s = await started()
        await api.setHoldChecks(true)
        let before = await watchCalls()
        s.send(.primary)
        await eventually("check in flight") { await api.heldCheckCount == 1 }
        #expect(s.watchGate == .paused)
        clock.advance(by: .seconds(1))  // past the interval sleep (2.5 s since the first call)
        clock.advance(by: .seconds(2))
        await settle()
        #expect(await watchCalls() == before)
        await api.releaseChecks()
        await eventually("pass") { s.lens.isPass }
        #expect(s.watchGate == .paused, "a pass screen pauses the watcher")
        await settle()
        #expect(await watchCalls() == before)
        s.send(.dismiss)  // leave the pass screen before its auto-advance
        #expect(s.lens.stepIdx == 1)
        await eventually("resumes") { await watchCalls() > before }
    }

    @Test func pausedWhileTalkingAndInTheBackground() async throws {
        let s = await started()
        await expectPause("talking", s) { s.setTalking(true) } resume: { s.setTalking(false) }
        await expectPause("background", s) { s.setAppActive(false) } resume: { s.setAppActive(true) }
    }

    @Test func pausedWhileTheFrameSourceIsUnavailable() async throws {
        let s = await started()
        frames.frame = nil
        s.watcherSettingsDidChange()
        #expect(s.watchIndicator == .paused)
        clock.advance(by: .seconds(10))
        await settle()
        #expect(await watchCalls() == 1)
        frames.frame = Data(repeating: 1, count: 10)
        clock.advance(by: .milliseconds(2500))
        await eventually("resumes") { await watchCalls() == 2 }
        await idle()
        #expect(s.watchIndicator == .active)
    }

    @Test func stepChangeDropsTheInFlightAnswer() async throws {
        let s = await started()
        await api.enqueueWatch(.success(watchResponse(.warn, mistake)), .success(watchResponse(.warn, mistake)))
        await tick()
        #expect(s.watcher.debouncer.streakCount == 1)
        await api.setHoldWatches(true)
        clock.advance(by: .milliseconds(2500))
        await eventually("call in flight") { await api.heldWatchCount == 1 }
        s.send(.next)
        s.send(.previous)  // back on step 1 before the answer lands: still a stale request
        await api.releaseWatches()
        await idle()
        #expect(!s.lens.isFix, "an answer sent for the earlier visit must not raise a warning")
        #expect(s.watcher.debouncer.streakCount == 0)
        #expect(await events(.warningShown).isEmpty)
    }

    // MARK: Warning behaviour (IOS-04.3)

    @Test func alertShowsProactiveWarningSpeaksAndPostsOnce() async throws {
        let s = await started()
        await raiseWarning(s)
        guard case .fix(let card, let headline, let fix, let proactive) = s.lens else {
            Issue.record("expected a fix screen")
            return
        }
        #expect(card.idx == 1 && headline == "Nori turned" && fix == "Long edge toward you" && proactive)
        #expect(speech.spoken.last == .init(text: "Turn the nori.", priority: .result))
        #expect(s.activeWarningID == mistake)
        await eventually("event") { await events(.warningShown).count == 1 }
        let shown = try #require(await events(.warningShown).first)
        #expect(shown.payload == ["mistake_id": .string(mistake)])
        #expect(shown.stepID == recipe.steps[0].id)
        #expect(log.entries.first?.outcome == .alert)
        // The watcher is paused behind the warning.
        #expect(s.watchGate == .paused)
        await settle()
        #expect(await events(.warningShown).count == 1)
        #expect(await events(.warningDismissed).isEmpty)
    }

    @Test func emptyStringsFallBackToTheStepsWatchFor() async throws {
        let s = await started()
        await api.enqueueWatch(.success(watchResponse(.warn, mistake)), .success(watchResponse(.warn, mistake)))
        await tick()
        await tick()
        await eventually("warning") { s.lens.isFix }
        let w = try #require(recipe.steps[0].watchFors.first)
        #expect(s.lens == .fix(try #require(s.lens.card), headline: w.headline, fix: w.fix, proactive: true))
        #expect(speech.spoken.last == .init(text: w.spoken, priority: .result))
    }

    @Test func dismissReturnsToStepPostsOnceAndMutesTwentySeconds() async throws {
        let s = await started()
        await raiseWarning(s)
        s.send(.dismiss)
        #expect(s.lens.stepIdx == 1)
        #expect(s.activeWarningID == nil)
        await eventually("event") { await events(.warningDismissed).count == 1 }
        #expect(await events(.warningDismissed).first?.payload == ["mistake_id": .string(mistake)])
        s.send(.dismiss)  // a second dismiss on the plain step does nothing
        await settle()
        #expect(await events(.warningDismissed).count == 1)

        // The same mistake keeps coming: silent for 20 s (ticks at 2.5 … 17.5 s after dismissal).
        await idle()
        for _ in 0..<7 {
            await api.enqueueWatch(.success(watchResponse(.warn, mistake)))
            await tick()
            #expect(s.lens.stepIdx == 1, "muted")
        }
        // 20 s after dismissal: alerts again (the streak kept counting while muted).
        await api.enqueueWatch(.success(watchResponse(.warn, mistake)))
        await tick()
        await eventually("warning again") { s.lens.isFix }
        #expect(clock.now.timeIntervalSince(clock.start) >= 20)
        await eventually("second warning_shown") { await events(.warningShown).count == 2 }
    }

    @Test func primaryOnWarningRunsACheckAndAPassClearsIt() async throws {
        let s = await started()
        await raiseWarning(s)
        await api.enqueueCheck(.success(checkResponse(.pass, headline: "Looks right")))
        s.send(.primary)
        await eventually("pass") { s.lens.isPass }
        #expect(await api.calls.contains { if case .check = $0 { true } else { false } })
        #expect(s.activeWarningID == nil)
        await settle()
        #expect(await events(.warningShown).count == 1)
        #expect(await events(.warningDismissed).isEmpty, "a check is not a dismissal")
    }

    @Test func warningDismissesItselfAfterTwelveSeconds() async throws {
        let s = await started()
        await raiseWarning(s)
        await eventually("auto-dismiss timer only") { clock.pendingCount == 1 }
        clock.advance(by: .milliseconds(11_900))
        await settle()
        #expect(s.lens.isFix, "not before 12 s")
        clock.advance(by: .milliseconds(100))
        await eventually("back to the step") { s.lens.stepIdx == 1 }
        await eventually("event") { await events(.warningDismissed).count == 1 }
        #expect(await events(.warningDismissed).first?.payload == ["mistake_id": .string(mistake)])
        #expect(s.watcher.debouncer.isMuted(mistake, at: clock.now), "counts as dismissed: muted")
        await settle()
        #expect(await events(.warningDismissed).count == 1)
    }

    @Test func manualDismissCancelsTheAutoDismiss() async throws {
        let s = await started()
        await raiseWarning(s)
        s.send(.dismiss)
        clock.advance(by: .seconds(13))
        await settle()
        #expect(await events(.warningDismissed).count == 1)
    }

    @Test func nextDuringWarningLeavesItWithoutDismissal() async throws {
        let s = await started()
        await raiseWarning(s)
        s.send(.next)
        #expect(s.lens.stepIdx == 2)
        #expect(s.activeWarningID == nil)
        clock.advance(by: .seconds(13))
        await settle()
        #expect(s.lens.stepIdx == 2)
        #expect(await events(.warningDismissed).isEmpty)
    }

    // MARK: Settings and lifetime

    @Test func settingsApplyWithoutRestartingTheSession() async throws {
        let s = await started()
        config.value.enabled = false
        s.watcherSettingsDidChange()
        #expect(s.watchIndicator == .off)
        #expect(s.lens.card?.watching == .off)
        clock.advance(by: .seconds(10))
        await settle()
        #expect(await watchCalls() == 1)

        config.value.enabled = true
        s.watcherSettingsDidChange()
        await eventually("on again") { await watchCalls() == 2 }
        await idle()
        #expect(s.lens.card?.watching == .active)
    }

    @Test func stopStopsTheWatcher() async throws {
        let s = await started()
        #expect(s.watcher.isRunning)
        s.stop()
        #expect(!s.watcher.isRunning)
        clock.advance(by: .seconds(10))
        await settle()
        #expect(await watchCalls() == 1)
    }

    @Test func doneStopsTheWatcherAndRestartResumesIt() async throws {
        let s = await started()
        for _ in recipe.steps { s.send(.next) }
        await eventually("done") { s.isDone }
        #expect(!s.watcher.isRunning)
        s.restart()
        await eventually("step 1") { s.lens.stepIdx == 1 }
        #expect(s.watcher.isRunning)
        await eventually("interval timer") { clock.pendingCount >= 1 }
        clock.advance(by: .seconds(3))
        await eventually("watching again") { await watchCalls() == 2 }
    }
}
