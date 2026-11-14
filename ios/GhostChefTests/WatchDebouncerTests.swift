import Foundation
import Testing

@testable import GhostChef

func watchResponse(
    _ status: WatchStatus, _ mistakeID: String? = nil, confidence: Double = 0.9, headline: String = "",
    fix: String = "", spoken: String = ""
) -> WatchResponse {
    WatchResponse(
        requestID: "", stepID: "", status: status, mistakeID: mistakeID, headline: headline, fix: fix,
        spoken: spoken, confidence: confidence, latencyMs: 10, model: "mock")
}

/// IOS-04.1 acceptance: the debounce rules of API-CONTRACT §3.3 as pure logic.
@Suite("WatchDebouncer")
struct WatchDebouncerTests {
    let t0 = Date(timeIntervalSince1970: 1_800_000_000)
    func at(_ s: TimeInterval) -> Date { t0.addingTimeInterval(s) }

    @Test func twoWarnsWithTheSameIDAlertOnTheSecond() {
        var d = WatchDebouncer()
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(0)) == nil)
        let alert = d.ingest(watchResponse(.warn, "a", headline: "Too much rice"), at: at(2.5))
        #expect(alert?.mistakeID == "a")
        #expect(alert?.headline == "Too much rice")
    }

    @Test func differentIDsDoNotAlert() {
        var d = WatchDebouncer()
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(0)) == nil)
        #expect(d.ingest(watchResponse(.warn, "b"), at: at(2.5)) == nil)
        // …but b then b does.
        #expect(d.ingest(watchResponse(.warn, "b"), at: at(5))?.mistakeID == "b")
    }

    @Test func okBetweenWarnsBreaksTheStreak() {
        var d = WatchDebouncer()
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(0)) == nil)
        #expect(d.ingest(watchResponse(.ok), at: at(2.5)) == nil)
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(5)) == nil)
    }

    @Test func belowThresholdWarnDoesNotCount() {
        var d = WatchDebouncer()
        #expect(d.ingest(watchResponse(.warn, "a", confidence: 0.69), at: at(0)) == nil)
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(2.5)) == nil, "the low one must not start a streak")
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(5)) != nil)

        // A low one in the middle breaks a streak.
        var e = WatchDebouncer()
        _ = e.ingest(watchResponse(.warn, "a"), at: at(0))
        #expect(e.ingest(watchResponse(.warn, "a", confidence: 0.5), at: at(2.5)) == nil)
        #expect(e.ingest(watchResponse(.warn, "a"), at: at(5)) == nil)

        // Exactly at the threshold counts; the threshold is a runtime value.
        var f = WatchDebouncer(threshold: 0.8)
        _ = f.ingest(watchResponse(.warn, "a", confidence: 0.8), at: at(0))
        #expect(f.ingest(watchResponse(.warn, "a", confidence: 0.8), at: at(2.5)) != nil)
        var g = WatchDebouncer(threshold: 0.95)
        _ = g.ingest(watchResponse(.warn, "a", confidence: 0.9), at: at(0))
        #expect(g.ingest(watchResponse(.warn, "a", confidence: 0.9), at: at(2.5)) == nil)
    }

    @Test func errorBreaksTheStreak() {
        var d = WatchDebouncer()
        _ = d.ingest(watchResponse(.warn, "a"), at: at(0))
        #expect(d.recordError() == false)
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(5)) == nil)
    }

    @Test func dismissedIDIsSilentForTwentySecondsThenAlertsAgain() {
        var d = WatchDebouncer()
        _ = d.ingest(watchResponse(.warn, "a"), at: at(0))
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(2.5)) != nil)
        d.dismissed(mistakeID: "a", at: at(3))

        // Muted from 3 s to 23 s, however long the streak gets.
        for s in stride(from: 5.0, through: 22.5, by: 2.5) {
            #expect(d.ingest(watchResponse(.warn, "a"), at: at(s)) == nil, "muted at \(s) s")
        }
        #expect(d.isMuted("a", at: at(22.9)))
        #expect(!d.isMuted("a", at: at(23)))
        // Other ids are not muted.
        _ = d.ingest(watchResponse(.warn, "b"), at: at(10))
        #expect(d.ingest(watchResponse(.warn, "b"), at: at(12.5)) != nil)

        // After the window: alerts again (the streak restarted while muted keeps counting).
        var e = WatchDebouncer()
        e.dismissed(mistakeID: "a", at: at(0))
        #expect(e.ingest(watchResponse(.warn, "a"), at: at(19)) == nil)
        #expect(e.ingest(watchResponse(.warn, "a"), at: at(19.9)) == nil)
        #expect(e.ingest(watchResponse(.warn, "a"), at: at(20)) != nil)
    }

    @Test func alertStartsANewStreak() {
        var d = WatchDebouncer()
        _ = d.ingest(watchResponse(.warn, "a"), at: at(0))
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(2.5)) != nil)
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(5)) == nil, "the third in a row is not a second alert")
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(7.5)) != nil)
    }

    @Test func threeErrorsInARowReturnTrue() {
        var d = WatchDebouncer()
        #expect(d.recordError() == false)
        #expect(d.recordError() == false)
        #expect(d.recordError() == true)
        // The count starts over afterwards.
        #expect(d.recordError() == false)

        // A success resets the error count.
        var e = WatchDebouncer()
        _ = e.recordError()
        _ = e.recordError()
        _ = e.ingest(watchResponse(.ok), at: at(0))
        #expect(e.recordError() == false)
        #expect(e.recordError() == false)
        #expect(e.recordError() == true)
    }

    @Test func resetClearsEverything() {
        var d = WatchDebouncer()
        _ = d.ingest(watchResponse(.warn, "a"), at: at(0))
        d.dismissed(mistakeID: "b", at: at(0))
        _ = d.recordError()
        _ = d.ingest(watchResponse(.warn, "c"), at: at(1))
        _ = d.recordError()
        d.reset()
        #expect(d.streakID == nil && d.streakCount == 0 && d.errorCount == 0 && d.mutedUntil.isEmpty)
        #expect(!d.isMuted("b", at: at(1)))
        // A warn right after reset is only the first of a streak.
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(2)) == nil)
        #expect(d.ingest(watchResponse(.warn, "a"), at: at(3)) != nil)
        // The error count restarted too.
        var e = WatchDebouncer()
        _ = e.recordError()
        _ = e.recordError()
        e.reset()
        #expect(e.recordError() == false)
    }

    @Test func warnWithoutMistakeIDNeverCounts() {
        var d = WatchDebouncer()
        _ = d.ingest(watchResponse(.warn, nil), at: at(0))
        #expect(d.ingest(watchResponse(.warn, nil), at: at(2.5)) == nil)
        _ = d.ingest(watchResponse(.unknown, "a"), at: at(5))
        #expect(d.ingest(watchResponse(.unknown, "a"), at: at(7.5)) == nil)
    }
}
