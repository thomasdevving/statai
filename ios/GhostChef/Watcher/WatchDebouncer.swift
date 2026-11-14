import Foundation

/// The watcher's debounce rules (API-CONTRACT §3.3), as pure logic: no I/O and no clock of its own.
/// The web simulator implements the same rules; keep the two identical.
///
/// - A streak counts only `warn` responses with the **same** `mistake_id` and
///   `confidence ≥ threshold`. An `ok`, a different id, a low confidence, or an error breaks it.
/// - `requiredConsecutive` such responses in a row raise one alert; the streak then starts over.
/// - A dismissed id is muted for `muteSeconds` and never alerts while muted.
/// - Three errors in a row tell the caller to pause; any success resets the error count.
struct WatchDebouncer: Sendable, Equatable {
    var threshold: Double = 0.7
    var requiredConsecutive = 2
    var muteSeconds: TimeInterval = 20
    var errorsBeforePause = 3

    private(set) var streakID: String?
    private(set) var streakCount = 0
    private(set) var errorCount = 0
    private(set) var mutedUntil: [String: Date] = [:]

    /// Returns the response to alert on, or nil.
    mutating func ingest(_ r: WatchResponse, at now: Date) -> WatchResponse? {
        errorCount = 0
        guard r.status == .warn, let id = r.mistakeID, !id.isEmpty, r.confidence >= threshold else {
            breakStreak()
            return nil
        }
        if streakID == id {
            streakCount += 1
        } else {
            streakID = id
            streakCount = 1
        }
        guard !isMuted(id, at: now), streakCount >= requiredConsecutive else { return nil }
        breakStreak()
        return r
    }

    /// Starts the mute window for `mistakeID`.
    mutating func dismissed(mistakeID: String, at now: Date) {
        mutedUntil[mistakeID] = now.addingTimeInterval(muteSeconds)
        breakStreak()
    }

    /// On step change: forgets the streak, the error count, and every mute.
    mutating func reset() {
        breakStreak()
        errorCount = 0
        mutedUntil = [:]
    }

    /// Records a failed `/watch`. Returns true on the third error in a row: the caller pauses
    /// (15 s) and the count starts over.
    mutating func recordError() -> Bool {
        breakStreak()
        errorCount += 1
        guard errorCount >= errorsBeforePause else { return false }
        errorCount = 0
        return true
    }

    func isMuted(_ mistakeID: String, at now: Date) -> Bool {
        guard let until = mutedUntil[mistakeID] else { return false }
        return now < until
    }

    private mutating func breakStreak() {
        streakID = nil
        streakCount = 0
    }
}
