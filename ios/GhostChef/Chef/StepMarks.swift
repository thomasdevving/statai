import Foundation

/// Collects the chef's "new step" marks during one take (IOS-08.3).
/// Marks are seconds since the recording started, strictly ascending; two marks within 1 s
/// collapse into one (a double-registered pinch must not split a step).
struct StepMarkCollector: Equatable, Sendable {
    static let collapseWindow: TimeInterval = 1

    private(set) var startedAt: Date?
    private(set) var marks: [Double] = []

    /// The step the chef is on: 1 before any mark, then 1 + marks.
    var currentStep: Int { marks.count + 1 }

    mutating func start(at date: Date) {
        startedAt = date
        marks = []
    }

    /// Records a mark. Returns the step number it starts, or nil when it was ignored
    /// (not recording, before the start, or within 1 s of the previous mark).
    @discardableResult
    mutating func mark(at date: Date) -> Int? {
        guard let startedAt else { return nil }
        let seconds = (date.timeIntervalSince(startedAt) * 100).rounded() / 100
        guard seconds >= 0 else { return nil }
        if let last = marks.last, seconds - last < Self.collapseWindow { return nil }
        marks.append(seconds)
        return currentStep
    }

    /// Between takes.
    mutating func reset() {
        startedAt = nil
        marks = []
    }
}

/// "03:12" for the REC timer.
func recordingClock(_ seconds: TimeInterval) -> String {
    let s = max(0, Int(seconds.rounded(.down)))
    return String(format: "%02d:%02d", s / 60, s % 60)
}
