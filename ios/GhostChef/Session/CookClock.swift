import Foundation

/// Every timer in the cook-along goes through this, so tests can advance time without sleeping.
protocol CookClock: Sendable {
    func sleep(for duration: Duration) async throws
    /// The current time on this clock (the watcher's mute windows and intervals use it).
    var now: Date { get }
}

struct SystemCookClock: CookClock {
    /// Without an explicit tolerance the system coalesces long timers: a 12 s sleep was seen
    /// firing ~0.8 s late in the simulator. The screen and watcher timings are part of the contract.
    static let tolerance = Duration.milliseconds(20)

    func sleep(for duration: Duration) async throws {
        try await Task.sleep(for: duration, tolerance: Self.tolerance)
    }

    var now: Date { Date() }
}

extension Duration {
    var timeInterval: TimeInterval {
        let c = components
        return Double(c.seconds) + Double(c.attoseconds) / 1e18
    }

    init(timeInterval: TimeInterval) {
        self = .nanoseconds(Int64((timeInterval * 1e9).rounded()))
    }
}
