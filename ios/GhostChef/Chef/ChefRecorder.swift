import Foundation
import Observation

// IOS-08.3: Chef mode — consent, record (glasses or phone), step marks, name the take.
// Device pieces come in as protocols so the state machine is unit-tested without a device.

/// Writes one take (video + mic) to an MP4. `AVTakeCapture` is the device implementation.
@MainActor
protocol TakeCapturing: AnyObject {
    /// Which camera the next take uses; decided when the capture is made.
    var source: TakeSource { get }
    func start(writingTo url: URL) async throws
    /// Finalizes the file. Returns its real duration.
    func stop() async throws -> TakeCaptureResult
}

struct TakeCaptureResult: Equatable, Sendable {
    var durationS: Double
    var width: Int
    var height: Int
    var videoFrames: Int
    var hasAudio: Bool
}

/// "● REC 03:12" and "Step N" in the lens (glasses only; no-op without a display).
@MainActor
protocol ChefLens: AnyObject {
    func showRecording(elapsed: TimeInterval, step: Int, justMarked: Bool)
    func clear()
}

/// The short click on every mark.
@MainActor
protocol ChefFeedback: AnyObject {
    func markClick()
}

@MainActor
@Observable
final class ChefRecorder {
    enum Phase: Equatable {
        case idle
        case recording
        case finishing
        /// Recorded and saved on the phone; waiting for a title.
        case naming(TakeRecord)
        case failed(String)
    }

    static let consentText =
        "Everyone in this recording agrees to it being processed by Google Gemini and shown in the Ghost Chef demo."
    static let maxTitleLength = 80
    /// "Step 3 marked" stays in the lens this long.
    static let markedBadge: TimeInterval = 2

    private(set) var phase: Phase = .idle
    /// Must be on before a take can start; sent as `consent: true`.
    var consentGiven = false
    private(set) var marks = StepMarkCollector()
    private(set) var elapsed: TimeInterval = 0
    private(set) var lastMarkedStep: Int?

    var source: TakeSource { capture.source }
    var canStart: Bool { consentGiven && (phase == .idle || isFailed) }
    var isRecording: Bool { phase == .recording }

    @ObservationIgnored private let capture: any TakeCapturing
    @ObservationIgnored private let store: TakeStore
    @ObservationIgnored private let clock: any CookClock
    @ObservationIgnored private weak var lens: (any ChefLens)?
    @ObservationIgnored private weak var feedback: (any ChefFeedback)?
    @ObservationIgnored private var takeID: String?
    @ObservationIgnored private var startedAt: Date?
    @ObservationIgnored private var markedAt: Date?
    @ObservationIgnored private var ticker: Task<Void, Never>?

    init(
        capture: any TakeCapturing, store: TakeStore, clock: any CookClock = SystemCookClock(),
        lens: (any ChefLens)? = nil, feedback: (any ChefFeedback)? = nil
    ) {
        self.capture = capture
        self.store = store
        self.clock = clock
        self.lens = lens
        self.feedback = feedback
    }

    private var isFailed: Bool { if case .failed = phase { true } else { false } }

    /// The lens and the click come after init: the lens calls back into the recorder (its
    /// "New step" button), so it is made once the recorder exists. Both are held weakly.
    func attach(lens: (any ChefLens)?, feedback: (any ChefFeedback)?) {
        self.lens = lens
        self.feedback = feedback
    }

    // MARK: Record

    func start() async {
        guard consentGiven else {
            phase = .failed("Recording needs everyone's consent first.")
            return
        }
        guard phase == .idle || isFailed else { return }
        let id = store.newTakeID()
        do {
            try store.prepare()
            try await capture.start(writingTo: store.videoURL(for: id))
        } catch {
            phase = .failed("Couldn't start recording: \(error.localizedDescription)")
            return
        }
        takeID = id
        let now = clock.now
        startedAt = now
        marks.start(at: now)
        elapsed = 0
        lastMarkedStep = nil
        markedAt = nil
        phase = .recording
        updateLens()
        startTicker()
    }

    /// A pinch, the phone button, or the lens button: the chef starts a new step.
    func mark() {
        guard phase == .recording else { return }
        let now = clock.now
        guard let step = marks.mark(at: now) else { return }
        lastMarkedStep = step
        markedAt = now
        feedback?.markClick()
        // The lens shows it on the next one-second tick (lens updates at most once a second).
    }

    func stop() async {
        guard phase == .recording, let id = takeID else { return }
        ticker?.cancel()
        ticker = nil
        phase = .finishing
        lens?.clear()
        do {
            let result = try await capture.stop()
            // A mark in the last instant can fall after the written end; drop it.
            let kept = marks.marks.filter { $0 < result.durationS }
            let record = TakeRecord(
                id: id, source: capture.source, recordedAt: startedAt ?? clock.now, durationS: result.durationS,
                stepMarksS: kept, consent: consentGiven)
            try store.save(record)
            phase = .naming(record)
        } catch {
            phase = .failed("The recording could not be saved: \(error.localizedDescription)")
        }
        takeID = nil
    }

    // MARK: Name

    /// Title required (≤ 80 characters), chef name optional. Returns the saved record, ready to
    /// upload, or nil with the reason in `titleError`.
    private(set) var titleError: String?

    @discardableResult
    func finish(title rawTitle: String, chefName rawChef: String) -> TakeRecord? {
        guard case .naming(var record) = phase else { return nil }
        let title = rawTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else {
            titleError = "Give the recipe a title."
            return nil
        }
        guard title.count <= Self.maxTitleLength else {
            titleError = "Keep the title to \(Self.maxTitleLength) characters."
            return nil
        }
        titleError = nil
        let chef = rawChef.trimmingCharacters(in: .whitespacesAndNewlines)
        record.title = title
        record.chefName = chef.isEmpty ? nil : chef
        do {
            try store.save(record)
        } catch {
            titleError = "Couldn't save: \(error.localizedDescription)"
            return nil
        }
        reset()
        return record
    }

    /// Throws the take away (and its file).
    func discard() {
        if case .naming(let record) = phase { store.delete(record.id) }
        reset()
    }

    /// Ready for the next take; consent is asked again.
    func reset() {
        ticker?.cancel()
        ticker = nil
        marks.reset()
        elapsed = 0
        lastMarkedStep = nil
        consentGiven = false
        titleError = nil
        phase = .idle
    }

    // MARK: Ticker

    private func startTicker() {
        ticker?.cancel()
        let clock = clock
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                do { try await clock.sleep(for: .seconds(1)) } catch { return }
                guard let self, self.phase == .recording else { return }
                self.updateLens()
            }
        }
    }

    private func updateLens() {
        guard let startedAt else { return }
        let now = clock.now
        elapsed = now.timeIntervalSince(startedAt)
        let justMarked = markedAt.map { now.timeIntervalSince($0) < Self.markedBadge } ?? false
        lens?.showRecording(elapsed: elapsed, step: marks.currentStep, justMarked: justMarked)
    }
}
