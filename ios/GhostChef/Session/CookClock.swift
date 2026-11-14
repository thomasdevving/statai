import Foundation

/// Every timer in the cook-along goes through this, so tests can advance time without sleeping.
protocol CookClock: Sendable {
    func sleep(for duration: Duration) async throws
}

struct SystemCookClock: CookClock {
    func sleep(for duration: Duration) async throws {
        try await Task.sleep(for: duration)
    }
}
