import Foundation
import Network
import Observation

/// Is there a network path at all (IOS-07.3)? Drives the "Offline" banner; cards and images keep
/// working from the cache, and the watcher and checks recover on their own when the path returns.
@MainActor
@Observable
final class NetworkMonitor {
    private(set) var isOnline = true
    @ObservationIgnored private let monitor = NWPathMonitor()

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let online = path.status == .satisfied
            Task { @MainActor in self?.isOnline = online }
        }
        monitor.start(queue: DispatchQueue(label: "ghostchef.network"))
    }

    deinit { monitor.cancel() }
}

/// Polls `GET /health` while a cook-along runs, for the one-line "Backend unreachable" banner on
/// the phone (IOS-07.3). The lens shows only the grey dot; nothing here touches it.
@MainActor
@Observable
final class BackendReachability {
    enum State: Equatable {
        case unknown
        case reachable(aiMode: String)
        case unreachable(String)
    }

    static let interval: Duration = .seconds(10)

    private(set) var state: State = .unknown
    @ObservationIgnored private let api: any GhostChefAPI
    @ObservationIgnored private let clock: any CookClock
    @ObservationIgnored private var task: Task<Void, Never>?

    init(api: any GhostChefAPI, clock: any CookClock = SystemCookClock()) {
        self.api = api
        self.clock = clock
    }

    func start() {
        guard task == nil else { return }
        task = Task { [weak self] in
            while !Task.isCancelled {
                await self?.checkOnce()
                guard let clock = self?.clock else { return }
                do { try await clock.sleep(for: Self.interval) } catch { return }
            }
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    func checkOnce() async {
        do {
            let health = try await api.health()
            state = .reachable(aiMode: health.aiMode)
        } catch is CancellationError {
        } catch {
            state = .unreachable(error.localizedDescription)
        }
    }

    var isUnreachable: Bool { if case .unreachable = state { true } else { false } }
}

/// Audio-only mode (IOS-07.1): speaks what `CookSession` does not already say when the screen
/// changes, so a whole session can be followed with eyes closed. Active only while `isActive()`.
@MainActor
final class SpokenLens {
    private let session: CookSession
    private let speech: any SpeechOutput
    private let tone: @MainActor () -> Void
    private let isActive: @MainActor () -> Bool
    private var previous: LensScreen?
    private var lastStepIdx: Int?
    private var running = false

    init(
        session: CookSession, speech: any SpeechOutput, tone: @escaping @MainActor () -> Void,
        isActive: @escaping @MainActor () -> Bool
    ) {
        self.session = session
        self.speech = speech
        self.tone = tone
        self.isActive = isActive
    }

    func start() {
        guard !running else { return }
        running = true
        observe()
    }

    func stop() { running = false }

    private func observe() {
        guard running else { return }
        let screen = withObservationTracking {
            session.lens
        } onChange: { [weak self] in
            Task { @MainActor in self?.observe() }
        }
        handle(screen)
    }

    func handle(_ screen: LensScreen) {
        defer {
            previous = screen
            if let idx = screen.card?.idx { lastStepIdx = idx }
        }
        guard isActive(), let narration = AudioOnlyNarration.narration(from: previous, to: screen, lastStepIdx: lastStepIdx)
        else { return }
        switch narration {
        case .speak(let text): speech.speak(text, priority: .info)
        case .checkingTone: tone()
        }
    }
}
