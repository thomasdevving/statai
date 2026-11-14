import Foundation
import Observation

/// Runtime knobs for the watcher, read on every tick so Settings changes apply without a restart.
struct WatcherConfig: Equatable, Sendable {
    var enabled = true
    /// `WATCH_THRESHOLD` (API-CONTRACT §3.3; `ai/STATUS.md` "Tuned values" once tuned).
    var threshold = 0.7
    /// Measured from the end of the previous call.
    var interval: Duration = .milliseconds(2500)

    static let disabled = WatcherConfig(enabled: false)
}

/// What the cook-along allows the watcher to do right now. `CookSession` computes it.
enum WatchGate: Equatable, Sendable {
    /// No cook-along running (preparing, Done, stopped): the dot is off and nothing is sent.
    case inactive
    /// The step has no `watch_fors`: the dot is off and no calls are made.
    case off
    /// Lens not on the step card, a check in flight, talking to Live, app in the background.
    case paused
    case open(stepID: String, sessionID: String?)
}

/// The side of `CookSession` the watcher talks to.
@MainActor
protocol WatcherHost: AnyObject {
    var watchGate: WatchGate { get }
    func watcher(didChangeIndicator indicator: WatchIndicator)
    func watcher(didAlert response: WatchResponse)
}

/// The last ten `/watch` results, for the readout in Settings (IOS-04.4) used to tune at the table.
@MainActor
@Observable
final class WatchLog {
    enum Outcome: String, Sendable {
        /// `warn` that completed a streak and raised the warning.
        case alert
        case ok, warn
        /// Arrived for an old step / request, or while paused: dropped without UI effect (§3.4).
        case stale
        /// `429` retryable: tick skipped, not counted as an error.
        case busy
        case error
    }

    struct Entry: Identifiable, Equatable, Sendable {
        let id: Int
        let at: Date
        let outcome: Outcome
        let mistakeID: String?
        let confidence: Double?
        /// What the server reports (`latency_ms`).
        let serverMs: Int?
        /// Measured on the phone, request to answer.
        let roundTripMs: Int
        let detail: String?
    }

    static let capacity = 10
    private(set) var entries: [Entry] = []
    @ObservationIgnored private var nextID = 0

    init() {}

    func record(
        _ outcome: Outcome, response: WatchResponse? = nil, roundTripMs: Int, detail: String? = nil, at: Date = .now
    ) {
        nextID += 1
        entries.insert(
            Entry(
                id: nextID, at: at, outcome: outcome, mistakeID: response?.mistakeID,
                confidence: response?.confidence, serverMs: response?.latencyMs, roundTripMs: roundTripMs,
                detail: detail),
            at: 0)
        if entries.count > Self.capacity { entries.removeLast(entries.count - Self.capacity) }
    }

    func clear() { entries = [] }
}

/// The proactive watcher (IOS-04.2, API-CONTRACT §3.3–§3.4). While the gate is open it grabs a
/// low-resolution frame, sends `/watch`, waits for the answer, then waits `interval` after that
/// answer before the next tick. Never two calls in flight. Responses go through the stale-result
/// rule and the debouncer; an alert is handed to the host.
///
/// The loop task holds the loop only weakly between steps, so dropping the session stops it; `stop()`
/// ends it at once.
@MainActor
final class WatcherLoop {
    enum Timing {
        /// After three errors in a row.
        static let errorPause = Duration.seconds(15)
    }

    struct Request: Sendable, Equatable {
        let stepID: String
        let requestID: String
        let sessionID: String?
    }

    weak var host: (any WatcherHost)?

    private(set) var indicator: WatchIndicator = .off
    private(set) var debouncer = WatchDebouncer()
    /// The most recent `/watch` request id (§3.4). Nil once handled or dropped.
    private(set) var latestRequestID: String?
    private(set) var isCallInFlight = false
    /// Set after three errors in a row; the loop sends nothing until then.
    private(set) var pausedUntil: Date?
    /// Grey dot after any network failure (watch or check) until the next success.
    private(set) var isOffline = false
    var isRunning: Bool { task != nil }

    private let api: any GhostChefAPI
    private let frames: any FrameSource
    private let clock: any CookClock
    private let config: @MainActor () -> WatcherConfig
    private let log: WatchLog?
    private var lastCallEnded: Date?

    nonisolated(unsafe) private var task: Task<Void, Never>?
    nonisolated(unsafe) private var wake: AsyncStream<Void>.Continuation?

    init(
        api: any GhostChefAPI, frames: any FrameSource, clock: any CookClock,
        config: @escaping @MainActor () -> WatcherConfig, log: WatchLog? = nil
    ) {
        self.api = api
        self.frames = frames
        self.clock = clock
        self.config = config
        self.log = log
    }

    deinit {
        task?.cancel()
        wake?.finish()
    }

    // MARK: Control

    func start() {
        guard task == nil else { return }
        let (stream, continuation) = AsyncStream.makeStream(
            of: Void.self, bufferingPolicy: .bufferingNewest(1))
        wake = continuation
        let api = api
        let frames = frames
        let clock = clock
        task = Task { [weak self] in
            var wakes = stream.makeAsyncIterator()
            while !Task.isCancelled {
                // `self` is only borrowed for the synchronous parts of each step.
                guard let plan = self?.nextPlan() else { return }
                switch plan {
                case .waitForChange:
                    guard await wakes.next() != nil else { return }
                case .sleep(let duration):
                    do { try await clock.sleep(for: duration) } catch { return }
                case .call(let request):
                    let started = ContinuousClock.now
                    guard
                        let frame = await frames.latestJPEG(
                            maxLongEdge: FrameSpec.watch.maxLongEdge, quality: FrameSpec.watch.quality)
                    else {
                        self?.frameMissing(request)
                        continue
                    }
                    let result: Result<WatchResponse, any Error>
                    do {
                        result = .success(
                            try await api.watch(
                                frame: frame, stepID: request.stepID, requestID: request.requestID,
                                sessionID: request.sessionID, capturedAt: Date()))
                    } catch {
                        result = .failure(error)
                    }
                    self?.finish(request, result, roundTrip: ContinuousClock.now - started)
                }
            }
        }
        refreshIndicator()
    }

    /// Stops completely: cancels the loop and drops any in-flight answer.
    func stop() {
        task?.cancel()
        task = nil
        wake?.finish()
        wake = nil
        latestRequestID = nil
        pausedUntil = nil
        refreshIndicator()
    }

    /// The host's gate, the frame source or the settings may have changed: re-evaluate now.
    func stateDidChange() {
        refreshIndicator()
        wake?.yield()
    }

    /// New step (or restart): reset the debouncer and drop the in-flight answer.
    func stepDidChange() {
        debouncer.reset()
        latestRequestID = nil
        stateDidChange()
    }

    /// The wearer dismissed a warning (or it timed out): mute that id for 20 s.
    func dismissed(mistakeID: String) {
        debouncer.dismissed(mistakeID: mistakeID, at: clock.now)
    }

    /// Network outcome of another call (`/check`): the dot is grey until the next success.
    func noteNetwork(reachable: Bool) {
        isOffline = !reachable
        refreshIndicator()
    }

    // MARK: Loop steps

    private enum Plan {
        case waitForChange
        case sleep(Duration)
        case call(Request)
    }

    private func nextPlan() -> Plan {
        let cfg = config()
        debouncer.threshold = cfg.threshold
        let now = clock.now
        if let until = pausedUntil {
            if now < until {
                refreshIndicator()
                return .sleep(Duration(timeInterval: until.timeIntervalSince(now)))
            }
            pausedUntil = nil
        }
        refreshIndicator()
        guard case .open(let stepID, let sessionID) = effectiveGate(cfg) else { return .waitForChange }
        // The frame source has no change notification: look again after one interval.
        guard frames.isAvailable else { return .sleep(cfg.interval) }
        if let last = lastCallEnded {
            let remaining = cfg.interval.timeInterval - now.timeIntervalSince(last)
            if remaining > 0.000_5 { return .sleep(Duration(timeInterval: remaining)) }
        }
        let request = Request(stepID: stepID, requestID: newRequestID(), sessionID: sessionID)
        latestRequestID = request.requestID
        isCallInFlight = true
        return .call(request)
    }

    private func frameMissing(_ request: Request) {
        isCallInFlight = false
        lastCallEnded = clock.now
        if latestRequestID == request.requestID { latestRequestID = nil }
    }

    private func finish(_ request: Request, _ result: Result<WatchResponse, any Error>, roundTrip: Duration) {
        isCallInFlight = false
        let now = clock.now
        lastCallEnded = now
        let roundTripMs = Int((roundTrip.timeInterval * 1000).rounded())
        // Stale-result rule (§3.4) plus the pause rule: only the latest request, for the step on
        // screen, while the gate is still open, may have any effect.
        var isCurrent = latestRequestID == request.requestID && !Task.isCancelled
        if case .open(let stepID, _) = effectiveGate(config()) {
            isCurrent = isCurrent && stepID.lowercased() == request.stepID.lowercased()
        } else {
            isCurrent = false
        }
        if latestRequestID == request.requestID { latestRequestID = nil }

        switch result {
        case .success(let response):
            guard isCurrent,
                response.requestID.lowercased() == request.requestID.lowercased(),
                response.stepID.lowercased() == request.stepID.lowercased()
            else {
                log?.record(.stale, response: response, roundTripMs: roundTripMs)
                return
            }
            isOffline = false
            let alert = debouncer.ingest(response, at: now)
            log?.record(
                alert != nil ? .alert : (response.status == .warn ? .warn : .ok), response: response,
                roundTripMs: roundTripMs)
            refreshIndicator()
            if let alert {
                print("[watch] alert \(alert.mistakeID ?? "?") @ \(alert.confidence)")
                host?.watcher(didAlert: alert)
            }
        case .failure(let error):
            if error is CancellationError { return }
            if let apiError = error as? APIError, apiError.status == 429, apiError.isRetryable {
                // Server says a call for this session is still running: skip this tick.
                log?.record(.busy, roundTripMs: roundTripMs, detail: "429")
                return
            }
            guard isCurrent else {
                log?.record(.stale, roundTripMs: roundTripMs, detail: error.localizedDescription)
                return
            }
            isOffline = true
            if debouncer.recordError() {
                pausedUntil = now.addingTimeInterval(Timing.errorPause.timeInterval)
                print("[watch] three errors in a row: pausing \(Timing.errorPause)")
            }
            log?.record(.error, roundTripMs: roundTripMs, detail: error.localizedDescription)
            refreshIndicator()
        }
    }

    // MARK: Indicator

    private func effectiveGate(_ cfg: WatcherConfig) -> WatchGate {
        guard let host, task != nil else { return .inactive }
        let gate = host.watchGate
        if gate == .inactive { return .inactive }
        return cfg.enabled ? gate : .off
    }

    private func refreshIndicator() {
        let new: WatchIndicator
        let gate: WatchGate =
            if task == nil, let host, host.watchGate != .inactive { .off } else { effectiveGate(config()) }
        switch gate {
        case .inactive:
            new = .off
        case _ where isOffline || pausedUntil != nil:
            new = .offline
        case .off:
            new = .off
        case .paused:
            new = .paused
        case .open:
            new = frames.isAvailable ? .active : .paused
        }
        guard new != indicator else { return }
        indicator = new
        host?.watcher(didChangeIndicator: new)
    }
}
