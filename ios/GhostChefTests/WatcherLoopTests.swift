import Foundation
import Testing

@testable import GhostChef

@MainActor
final class FakeWatcherHost: WatcherHost {
    weak var loop: WatcherLoop?
    var gate: WatchGate {
        didSet { loop?.stateDidChange() }
    }
    private(set) var indicators: [WatchIndicator] = []
    private(set) var alerts: [WatchResponse] = []

    init(gate: WatchGate) { self.gate = gate }

    var watchGate: WatchGate { gate }
    func watcher(didChangeIndicator indicator: WatchIndicator) { indicators.append(indicator) }
    func watcher(didAlert response: WatchResponse) { alerts.append(response) }
}

/// IOS-04.2 acceptance: the loop against `MockAPI` and a test clock.
@MainActor
@Suite("WatcherLoop")
struct WatcherLoopTests {
    let api: MockAPI
    let clock = TestClock()
    let frames = FakeFrameSource()
    let log = WatchLog()
    let host = FakeWatcherHost(gate: .open(stepID: "step-1", sessionID: "sess"))
    let loop: WatcherLoop
    final class ConfigBox { var value = WatcherConfig() }
    let config = ConfigBox()

    init() throws {
        api = MockAPI(recipe: try FixtureRecipe.load())
        let config = config
        loop = WatcherLoop(api: api, frames: frames, clock: clock, config: { config.value }, log: log)
        loop.host = host
        host.loop = loop
    }

    private func calls() async -> Int { await api.watchCallCount }

    private func watchCalls() async -> [(stepID: String, requestID: String)] {
        await api.calls.compactMap {
            if case .watch(let s, let r) = $0 { (s, r) } else { nil }
        }
    }

    /// Waits until the loop is sleeping out its interval after a call.
    private func waitForIntervalTimer() async {
        await eventually("interval timer armed") { clock.pendingCount == 1 && !loop.isCallInFlight }
    }

    // MARK: Interval and overlap

    @Test func firstTickIsImmediateAndCarriesStepAndSession() async throws {
        loop.start()
        await eventually("first call") { await calls() == 1 }
        let call = try #require(await watchCalls().first)
        #expect(call.stepID == "step-1")
        #expect(loop.indicator == .active)
        #expect(host.indicators.last == .active)
        await waitForIntervalTimer()
        #expect(log.entries.first?.outcome == .ok)
        loop.stop()
    }

    @Test func callsNeverOverlap() async throws {
        await api.setHoldWatches(true)
        loop.start()
        await eventually("call 1 in flight") { await api.heldWatchCount == 1 }
        // However much time passes, no second call while the first is unanswered.
        clock.advance(by: .seconds(30))
        loop.stateDidChange()
        host.gate = .open(stepID: "step-1", sessionID: "sess")
        await settle()
        #expect(await calls() == 1)
        #expect(clock.pendingCount == 0)

        for n in 2...4 {
            await api.releaseWatches()
            await waitForIntervalTimer()
            clock.advance(by: .milliseconds(2500))
            await eventually("call \(n) in flight") { await api.heldWatchCount == 1 }
            #expect(await calls() == n)
        }
        await api.releaseWatches()
        await waitForIntervalTimer()
        #expect(await api.maxWatchesInFlight == 1)
        loop.stop()
    }

    @Test func intervalIsMeasuredFromTheEndOfThePreviousCall() async throws {
        await api.setHoldWatches(true)
        loop.start()
        await eventually("call 1 in flight") { await api.heldWatchCount == 1 }
        clock.advance(by: .seconds(3))  // a slow answer: 3 s
        await api.releaseWatches()
        await waitForIntervalTimer()

        clock.advance(by: .milliseconds(2400))
        await settle()
        #expect(await calls() == 1, "2.4 s after the answer is too early")
        clock.advance(by: .milliseconds(100))
        await eventually("call 2 at 2.5 s after the answer") { await calls() == 2 }
        loop.stop()
    }

    @Test func intervalFollowsSettingsWithoutRestart() async throws {
        loop.start()
        await eventually("call 1") { await calls() == 1 }
        await waitForIntervalTimer()
        config.value.interval = .seconds(4)
        loop.stateDidChange()
        clock.advance(by: .milliseconds(2500))
        await settle()
        #expect(await calls() == 1, "the new 4 s interval applies to the running loop")
        await waitForIntervalTimer()
        clock.advance(by: .milliseconds(1500))
        await eventually("call 2 at 4 s") { await calls() == 2 }
        loop.stop()
    }

    // MARK: Pause conditions

    @Test func pausedGateSendsNothingAndResumesAfterwards() async throws {
        host.gate = .paused
        loop.start()
        await settle()
        #expect(await calls() == 0)
        #expect(loop.indicator == .paused)
        clock.advance(by: .seconds(30))
        await settle()
        #expect(await calls() == 0)

        host.gate = .open(stepID: "step-1", sessionID: "sess")
        await eventually("resumes") { await calls() == 1 }
        #expect(loop.indicator == .active)

        // Paused during the interval: the next tick waits for the gate.
        await waitForIntervalTimer()
        host.gate = .paused
        clock.advance(by: .milliseconds(2500))
        await settle()
        #expect(await calls() == 1)
        #expect(loop.indicator == .paused)
        host.gate = .open(stepID: "step-1", sessionID: "sess")
        await eventually("resumes again at once (interval already passed)") { await calls() == 2 }
        loop.stop()
    }

    @Test func answerArrivingWhilePausedIsDropped() async throws {
        await api.enqueueWatch(.success(watchResponse(.warn, "too_much_rice")), .success(watchResponse(.warn, "too_much_rice")))
        await api.setHoldWatches(true)
        loop.start()
        await eventually("call 1 in flight") { await api.heldWatchCount == 1 }
        host.gate = .paused  // e.g. the cook pressed Check
        await api.releaseWatches()
        await eventually("handled") { !loop.isCallInFlight }
        #expect(log.entries.first?.outcome == .stale)
        #expect(loop.debouncer.streakCount == 0, "a dropped answer must not count")

        host.gate = .open(stepID: "step-1", sessionID: "sess")
        // The dropped call still counts for the interval: the next one is 2.5 s after it.
        await waitForIntervalTimer()
        await settle()
        #expect(await calls() == 1)
        clock.advance(by: .milliseconds(2500))
        await eventually("call 2 in flight") { await api.heldWatchCount == 1 }
        await api.releaseWatches()
        await waitForIntervalTimer()
        #expect(host.alerts.isEmpty, "one counted warn is not two")
        loop.stop()
    }

    @Test func offGateAndDisabledWatcherMakeNoCalls() async throws {
        host.gate = .off  // a step without watch_fors
        loop.start()
        await settle()
        #expect(await calls() == 0)
        #expect(loop.indicator == .off)

        host.gate = .open(stepID: "step-1", sessionID: "sess")
        config.value.enabled = false
        loop.stateDidChange()
        await settle()
        #expect(await calls() == 0)
        #expect(loop.indicator == .off)

        config.value.enabled = true  // toggled in Settings: applies without a restart
        loop.stateDidChange()
        await eventually("on") { await calls() == 1 }
        #expect(loop.indicator == .active)
        loop.stop()
    }

    @Test func unavailableFrameSourcePausesUntilItReturns() async throws {
        frames.frame = nil
        loop.start()
        await settle()
        #expect(await calls() == 0)
        #expect(loop.indicator == .paused)
        frames.frame = Data(repeating: 1, count: 10)
        clock.advance(by: .milliseconds(2500))
        await eventually("resumes") { await calls() == 1 }
        #expect(loop.indicator == .active)
        loop.stop()
    }

    // MARK: Step change

    @Test func stepChangeResetsDebouncerAndDropsInFlightAnswer() async throws {
        await api.enqueueWatch(
            .success(watchResponse(.warn, "too_much_rice")), .success(watchResponse(.warn, "too_much_rice")),
            .success(watchResponse(.warn, "too_much_rice")))
        loop.start()
        await eventually("call 1") { await calls() == 1 }
        await waitForIntervalTimer()
        #expect(loop.debouncer.streakCount == 1)

        await api.setHoldWatches(true)
        clock.advance(by: .milliseconds(2500))
        await eventually("call 2 in flight") { await api.heldWatchCount == 1 }
        host.gate = .open(stepID: "step-2", sessionID: "sess")
        loop.stepDidChange()
        #expect(loop.debouncer.streakCount == 0)
        #expect(loop.latestRequestID == nil)
        await api.releaseWatches()
        await eventually("handled") { !loop.isCallInFlight }
        #expect(host.alerts.isEmpty, "the old step's second warn must not alert")
        #expect(log.entries.first?.outcome == .stale)

        // Next call is for the new step, after the interval.
        await waitForIntervalTimer()
        clock.advance(by: .milliseconds(2500))
        await eventually("call 3") { await api.heldWatchCount == 1 }
        #expect(await watchCalls().last?.stepID == "step-2")
        await api.releaseWatches()
        await waitForIntervalTimer()
        #expect(host.alerts.isEmpty)
        #expect(loop.debouncer.streakCount == 1)
        loop.stop()
    }

    // MARK: Alerts and errors

    @Test func twoMatchingWarnsAlertTheHost() async throws {
        await api.enqueueWatch(
            .success(watchResponse(.warn, "too_much_rice", headline: "Too much rice")),
            .success(watchResponse(.warn, "too_much_rice", headline: "Too much rice")))
        loop.start()
        await eventually("call 1") { await calls() == 1 }
        await waitForIntervalTimer()
        #expect(host.alerts.isEmpty)
        clock.advance(by: .milliseconds(2500))
        await eventually("alert") { host.alerts.count == 1 }
        #expect(host.alerts.first?.mistakeID == "too_much_rice")
        #expect(log.entries.map(\.outcome).prefix(2) == [.alert, .warn])
        loop.stop()
    }

    @Test func thresholdFollowsSettingsWithoutRestart() async throws {
        config.value.threshold = 0.95
        await api.enqueueWatch(
            .success(watchResponse(.warn, "a", confidence: 0.9)), .success(watchResponse(.warn, "a", confidence: 0.9)),
            .success(watchResponse(.warn, "a", confidence: 0.9)), .success(watchResponse(.warn, "a", confidence: 0.9)),
            .success(watchResponse(.warn, "a", confidence: 0.9)))
        loop.start()
        for n in 1...2 {
            await eventually("call \(n)") { await calls() == n }
            await waitForIntervalTimer()
            clock.advance(by: .milliseconds(2500))
        }
        await eventually("call 3") { await calls() == 3 }
        #expect(host.alerts.isEmpty)
        config.value.threshold = 0.85
        await waitForIntervalTimer()
        clock.advance(by: .milliseconds(2500))
        await eventually("call 4") { await calls() == 4 }
        await waitForIntervalTimer()
        clock.advance(by: .milliseconds(2500))
        await eventually("alert at the new threshold") { host.alerts.count == 1 }
        loop.stop()
    }

    @Test func retryable429SkipsATickWithoutCountingAsAnError() async throws {
        let busy = APIError(status: 429, code: .quotaExhausted, message: "busy", retryable: true)
        await api.enqueueWatch(.failure(busy), .failure(busy), .failure(busy), .failure(busy))
        loop.start()
        for n in 1...4 {
            await eventually("call \(n)") { await calls() == n }
            await waitForIntervalTimer()
            clock.advance(by: .milliseconds(2500))
        }
        await eventually("call 5") { await calls() == 5 }
        #expect(loop.pausedUntil == nil)
        #expect(loop.debouncer.errorCount == 0)
        #expect(!loop.isOffline)
        #expect(log.entries.contains { $0.outcome == .busy })
        loop.stop()
    }

    @Test func threeErrorsGoOfflineAndPauseFifteenSeconds() async throws {
        let down = APIError.network(message: "offline", timedOut: false)
        let timeout = APIError.network(message: "slow", timedOut: true)
        let server = APIError(status: 504, code: .modelTimeout, message: "slow", retryable: true)
        await api.enqueueWatch(.failure(down))
        loop.start()
        await eventually("call 1") { await calls() == 1 }
        await waitForIntervalTimer()
        #expect(loop.indicator == .offline, "any error turns the dot grey")
        #expect(loop.pausedUntil == nil)

        await api.enqueueWatch(.failure(timeout), .failure(server))
        clock.advance(by: .milliseconds(2500))
        await eventually("call 2") { await calls() == 2 }
        await waitForIntervalTimer()
        clock.advance(by: .milliseconds(2500))
        await eventually("call 3") { await calls() == 3 }
        await eventually("pause armed") { loop.pausedUntil != nil && clock.pendingCount == 1 }
        #expect(loop.indicator == .offline)

        clock.advance(by: .milliseconds(14_900))
        await settle()
        #expect(await calls() == 3, "paused for 15 s")
        clock.advance(by: .milliseconds(100))
        await eventually("resumes after 15 s") { await calls() == 4 }
        await waitForIntervalTimer()
        #expect(loop.indicator == .active, "the next success turns the dot green again")
        #expect(loop.pausedUntil == nil)
        loop.stop()
    }

    @Test func checkNetworkFailureGreysTheDotUntilTheNextSuccess() async throws {
        host.gate = .paused
        loop.start()
        loop.noteNetwork(reachable: false)
        #expect(loop.indicator == .offline)
        host.gate = .open(stepID: "step-1", sessionID: "sess")
        await eventually("call") { await calls() == 1 }
        await waitForIntervalTimer()
        #expect(loop.indicator == .active)
        loop.stop()
    }

    // MARK: Lifetime

    @Test func stopEndsTheLoopCompletely() async throws {
        await api.setHoldWatches(true)
        await api.enqueueWatch(.success(watchResponse(.warn, "a")), .success(watchResponse(.warn, "a")))
        loop.start()
        await eventually("call 1 in flight") { await api.heldWatchCount == 1 }
        loop.stop()
        #expect(!loop.isRunning)
        #expect(loop.indicator == .off)
        await api.releaseWatches()
        await settle()
        clock.advance(by: .seconds(60))
        await settle()
        #expect(await calls() == 1)
        #expect(clock.pendingCount == 0)
        #expect(log.entries.allSatisfy { $0.outcome == .stale })
    }

    @Test func loopIsReleasedWhenNothingHoldsIt() async throws {
        weak var weakLoop: WatcherLoop?
        do {
            let config = config
            let other = WatcherLoop(api: api, frames: frames, clock: clock, config: { config.value })
            other.host = host
            other.start()
            weakLoop = other
            await eventually("call") { await calls() == 1 }
            await eventually("sleeping") { clock.pendingCount == 1 }
        }
        await settle()
        #expect(weakLoop == nil, "the running task must not keep the loop alive")
        clock.advance(by: .seconds(10))
        await settle()
        #expect(await calls() == 1)
    }
}
