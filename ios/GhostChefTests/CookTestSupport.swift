import Foundation
import Testing

@testable import GhostChef

/// A clock that only moves when the test says so. Sleepers resume when `advance` passes their
/// deadline; cancelled sleepers throw `CancellationError`.
final class TestClock: CookClock, @unchecked Sendable {
    private struct Sleeper {
        let id: Int
        let deadline: Duration
        let continuation: CheckedContinuation<Void, any Error>
    }

    private let lock = NSLock()
    private var elapsed: Duration = .zero
    /// What `now` reads at `elapsed == 0`.
    let start = Date(timeIntervalSince1970: 1_800_000_000)
    private var sleepers: [Sleeper] = []
    private var cancelled: Set<Int> = []
    private var nextID = 0

    var pendingCount: Int { lock.withLock { sleepers.count } }
    var now: Date { start.addingTimeInterval(lock.withLock { elapsed }.timeInterval) }

    func sleep(for duration: Duration) async throws {
        let id = lock.withLock {
            nextID += 1
            return nextID
        }
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, any Error>) in
                let alreadyCancelled = lock.withLock {
                    if cancelled.contains(id) { return true }
                    sleepers.append(Sleeper(id: id, deadline: elapsed + duration, continuation: cont))
                    return false
                }
                if alreadyCancelled { cont.resume(throwing: CancellationError()) }
            }
        } onCancel: {
            let sleeper: Sleeper? = lock.withLock {
                cancelled.insert(id)
                if let i = sleepers.firstIndex(where: { $0.id == id }) { return sleepers.remove(at: i) }
                return nil
            }
            sleeper?.continuation.resume(throwing: CancellationError())
        }
    }

    func advance(by duration: Duration) {
        let due = lock.withLock {
            elapsed += duration
            let due = sleepers.filter { $0.deadline <= elapsed }
            sleepers.removeAll { $0.deadline <= elapsed }
            return due
        }
        due.forEach { $0.continuation.resume() }
    }
}

@MainActor
final class FakeSpeech: SpeechOutput {
    struct Utterance: Equatable {
        let text: String
        let priority: SpeechPriority
    }

    private(set) var spoken: [Utterance] = []
    private(set) var chimes = 0
    private(set) var stops = 0

    var isSpeaking: Bool { false }
    var texts: [String] { spoken.map(\.text) }

    func speak(_ text: String, priority: SpeechPriority) {
        spoken.append(Utterance(text: text, priority: priority))
    }

    func stop() { stops += 1 }
    func playChime() { chimes += 1 }
}

final class FakeFrameSource: FrameSource, @unchecked Sendable {
    var frame: Data? = Data(repeating: 0xAB, count: 20_000)
    var isAvailable: Bool { frame != nil }
    func start() async throws {}
    func stop() {}
    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? { frame }
}

/// Polls `condition` with short real sleeps; the session's own timers never run on real time.
@MainActor
func eventually(
    _ what: String, timeout: Duration = .seconds(3), sourceLocation: SourceLocation = #_sourceLocation,
    _ condition: @MainActor () async -> Bool
) async {
    let start = ContinuousClock.now
    while await !condition() {
        if ContinuousClock.now - start > timeout {
            Issue.record("Timed out waiting for: \(what)", sourceLocation: sourceLocation)
            return
        }
        try? await Task.sleep(for: .milliseconds(2))
    }
}

/// Lets in-flight tasks run, to show that something does *not* happen.
@MainActor
func settle() async {
    for _ in 0..<20 {
        await Task.yield()
        try? await Task.sleep(for: .milliseconds(2))
    }
}

func checkResponse(
    _ verdict: Verdict, headline: String = "", fix: String = "", spoken: String = "", mistakeID: String? = nil
) -> CheckResponse {
    CheckResponse(
        requestID: "", stepID: "", verdict: verdict, mistakeID: mistakeID, headline: headline, fix: fix,
        spoken: spoken, confidence: 0.9, latencyMs: 10, model: "mock")
}

extension LensScreen {
    var isPass: Bool { if case .pass = self { true } else { false } }
    var isFix: Bool { if case .fix = self { true } else { false } }
    var isChecking: Bool { if case .checking = self { true } else { false } }
    var isUnsure: Bool { if case .unsure = self { true } else { false } }
    var stepIdx: Int? { if case .step(let c) = self { c.idx } else { nil } }
    var noticeText: String? { if case .notice(let t) = self { t } else { nil } }
    var doneSummary: SessionSummary?? { if case .done(let s) = self { .some(s) } else { nil } }
}
