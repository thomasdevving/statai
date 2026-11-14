import Foundation
import Observation

/// The cook-along state machine (IOS-03.2). Produces `lens`; renderers only draw it.
/// Every dependency is injected so the whole loop runs in unit tests without a device.
/// Owns the proactive watcher (IOS-04) and decides when it may run (`watchGate`).
@MainActor
@Observable
final class CookSession: WatcherHost {
    enum Phase: Equatable {
        case idle
        /// Downloading the recipe's media before the first card (IOS-03.5).
        case preparing(done: Int, total: Int)
        case cooking
        case failed(String)
    }

    /// Screen timings from the batch spec.
    enum Timing {
        static let passAutoAdvance = Duration.seconds(2)
        static let unsureReturn = Duration.seconds(4)
        static let noticeReturn = Duration.seconds(3)
        static let checkRetryDelay = Duration.seconds(1)
        /// A proactive warning with no input dismisses itself (API-CONTRACT §3.3).
        static let warningAutoDismiss = Duration.seconds(12)
    }

    enum Notice {
        static let cantCheck = "Can't check right now"
        static let noConnection = "No connection"
        static let cameraOff = "Camera off"
        static let noFrame = "Camera not ready"
    }

    // MARK: State

    private(set) var phase: Phase = .idle {
        didSet { if phase != oldValue { watcher.stateDidChange() } }
    }
    private(set) var recipe: Recipe?
    /// 0-based index into `recipe.steps`.
    private(set) var stepIndex = 0
    private(set) var lens: LensScreen = .notice("Choose a recipe") {
        didSet { if lens != oldValue { watcher.stateDidChange() } }
    }
    private(set) var sessionID: String?
    /// The most recent `/check` request id (API-CONTRACT §3.4). Nil when none is pending.
    private(set) var latestCheckRequestID: String?
    /// The last applied check, for the operator's latency readout.
    private(set) var lastCheck: CheckResponse?
    private(set) var prefetchReport: ImageCache.Report?
    /// Driven by the watcher (IOS-04); `.offline` after a network error until the next success.
    private(set) var watchIndicator: WatchIndicator = .off
    /// The `mistake_id` of the proactive warning on screen, if any.
    private(set) var activeWarningID: String?
    /// False while the app is in the background (a watcher pause condition).
    private(set) var isAppActive = true
    /// True while the user talks to Gemini Live (IOS-05 sets it; a watcher pause condition).
    private(set) var isTalking = false

    var isActive: Bool { phase == .cooking }
    var isDone: Bool { if case .done = lens { true } else { false } }
    var currentStep: Step? {
        guard let steps = recipe?.steps, steps.indices.contains(stepIndex) else { return nil }
        return steps[stepIndex]
    }

    // MARK: Dependencies

    @ObservationIgnored private let api: any GhostChefAPI
    @ObservationIgnored private let frames: any FrameSource
    @ObservationIgnored private let speech: any SpeechOutput
    @ObservationIgnored private let clock: any CookClock
    @ObservationIgnored private let cache: ImageCache
    @ObservationIgnored private let deviceLabel: String?
    @ObservationIgnored let watcher: WatcherLoop
    /// Gemini Live (IOS-05). Nil when voice is off or not wired (tests, fixture previews).
    @ObservationIgnored var voice: VoiceController? {
        didSet { voice?.host = self }
    }
    /// The step a new session (and every restart) begins at, 1-based (IOS-07.6 "Start at step").
    @ObservationIgnored var startStep: @MainActor () -> Int = { 1 }
    /// The screen to return to when a Live turn ends (IOS-05.4).
    @ObservationIgnored private var lensBeforeTalking: LensScreen?

    @ObservationIgnored private var pendingCheck: Task<Void, Never>?
    @ObservationIgnored private var screenTimer: Task<Void, Never>?
    @ObservationIgnored private var startTask: Task<Void, Never>?
    @ObservationIgnored private var sessionEnded = false

    init(
        api: any GhostChefAPI, frames: any FrameSource, speech: any SpeechOutput,
        clock: any CookClock = SystemCookClock(), cache: ImageCache = ImageCache(),
        deviceLabel: String? = nil,
        watchConfig: @escaping @MainActor () -> WatcherConfig = { .disabled },
        watchLog: WatchLog? = nil
    ) {
        self.api = api
        self.frames = frames
        self.speech = speech
        self.clock = clock
        self.cache = cache
        self.deviceLabel = deviceLabel
        watcher = WatcherLoop(api: api, frames: frames, clock: clock, config: watchConfig, log: watchLog)
        watcher.host = self
    }

    // MARK: Start / stop

    /// Loads the recipe from the API, then starts it.
    func start(recipeID: String) async {
        phase = .preparing(done: 0, total: 0)
        lens = .notice("Preparing…")
        do {
            let recipe = try await api.recipe(id: recipeID)
            await start(recipe: recipe)
        } catch is CancellationError {
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }

    /// Downloads every reference image and clip, opens a session, shows step 1.
    func start(recipe: Recipe) async {
        cancelTimers()
        guard !recipe.steps.isEmpty else {
            phase = .failed("This recipe has no steps yet. It may still be processing.")
            return
        }
        self.recipe = recipe
        phase = .preparing(done: 0, total: 0)
        lens = .notice("Preparing \(recipe.steps.count) steps…")
        let report = await cache.prefetch(steps: recipe.steps) { [weak self] done, total in
            Task { @MainActor in
                guard let self, case .preparing = self.phase else { return }
                self.phase = .preparing(done: done, total: total)
            }
        }
        guard !Task.isCancelled else { return }
        prefetchReport = report
        await openSession(recipe: recipe)
    }

    /// The demo reset (IOS-03.6): ends the current session and starts a new one at step 1,
    /// reusing the media already on disk.
    func restart() {
        guard let recipe else { return }
        cancelTimers()
        speech.stop()
        voice?.stop()
        endSessionInBackground()
        startTask?.cancel()
        startTask = Task { await openSession(recipe: recipe) }
    }

    /// Leaving the cook-along: stop timers and speech, close the session on the server.
    func stop() {
        cancelTimers()
        watcher.stop()
        voice?.stop()
        startTask?.cancel()
        speech.stop()
        endSessionInBackground()
        phase = .idle
    }

    private func openSession(recipe: Recipe) async {
        sessionEnded = false
        sessionID = nil
        lastCheck = nil
        do {
            sessionID = try await api.createSession(recipeID: recipe.id, deviceLabel: deviceLabel).sessionID
        } catch is CancellationError {
            return
        } catch {
            // Cooking works without a session; only the Done summary is lost.
            log("POST /sessions failed: \(error.localizedDescription)")
        }
        guard !Task.isCancelled else { return }
        let start = min(max(startStep(), 1), recipe.steps.count) - 1
        stepIndex = start
        activeWarningID = nil
        lensBeforeTalking = nil
        isTalking = false
        watcher.stepDidChange()
        phase = .cooking
        showStep()
        if start > 0 {
            // The monitor follows step_change events; tell it the demo starts mid-recipe.
            postEvent(
                .stepChange, stepID: recipe.steps[start].id,
                payload: [
                    "from_idx": .number(Double(recipe.steps[0].idx)),
                    "to_idx": .number(Double(recipe.steps[start].idx)),
                    "via": .string(InputVia.tap.rawValue),
                ])
        }
        watcher.start()
        speakLens(priority: .info)
        // IOS-05.4: after the first card is up, connect Live in the background.
        voice?.start()
    }

    // MARK: Inputs

    func send(_ input: CookInput, via: InputVia = .tap) {
        guard phase == .cooking else { return }
        if input == .repeatInstruction {
            if let step = currentStep {
                speech.speak(step.instruction.isEmpty ? step.keyLine : step.instruction, priority: .result)
            }
            return
        }
        switch (input, lens) {
        case (_, .done):
            return  // Only "Restart session" leaves the Done screen.
        case (.primary, .checking):
            return  // One check at a time.
        case (.primary, .pass):
            advance(via: via)
        case (.primary, _):
            startCheck()
        case (.next, _):
            advance(via: via)
        case (.previous, _):
            goToStep(stepIndex - 1, via: via)
        case (.dismiss, .step):
            return
        case (.dismiss, .fix(_, _, _, true)):
            dismissWarning()
        case (.dismiss, _):
            showStep()
        case (.showMe, _):
            guard let card = currentCard() else { return }
            cancelTimers()
            lens = .showMe(card)
            postEvent(.showMe, stepID: currentStep?.id)
        case (.repeatInstruction, _):
            return  // Handled above.
        }
    }

    // MARK: Check flow

    private func startCheck() {
        guard let step = currentStep, let card = currentCard() else { return }
        cancelTimers()
        // "I fixed it, look now": a check from a proactive warning replaces it.
        activeWarningID = nil
        lens = .checking(card)
        let requestID = newRequestID()
        latestCheckRequestID = requestID
        pendingCheck = Task { [weak self] in
            await self?.runCheck(stepID: step.id, requestID: requestID)
        }
    }

    private func runCheck(stepID: String, requestID firstRequestID: String) async {
        guard let frame = await frames.latestJPEG(
            maxLongEdge: FrameSpec.check.maxLongEdge, quality: FrameSpec.check.quality)
        else {
            guard isLatest(firstRequestID, stepID: stepID) else { return }
            showNotice(frames.isAvailable ? Notice.noFrame : Notice.cameraOff)
            return
        }
        var requestID = firstRequestID
        var retried = false
        while true {
            guard isLatest(requestID, stepID: stepID), !Task.isCancelled else { return }
            do {
                let response = try await api.check(
                    frame: frame, stepID: stepID, requestID: requestID, sessionID: sessionID,
                    capturedAt: .now)
                apply(response)
                return
            } catch is CancellationError {
                return
            } catch let error as APIError {
                guard isLatest(requestID, stepID: stepID) else { return }
                if !retried, Self.isRetriedOnce(error) {
                    retried = true
                    do { try await clock.sleep(for: Timing.checkRetryDelay) } catch { return }
                    // A retry is a new request: new id, and it becomes the one to accept.
                    guard isLatest(requestID, stepID: stepID) else { return }
                    requestID = newRequestID()
                    latestCheckRequestID = requestID
                    continue
                }
                log("check failed: \(error.localizedDescription)")
                if error.isNetwork, case .network(_, let timedOut) = error, !timedOut {
                    watcher.noteNetwork(reachable: false)
                    showNotice(Notice.noConnection)
                } else {
                    showNotice(Notice.cantCheck)
                }
                return
            } catch {
                guard isLatest(requestID, stepID: stepID) else { return }
                showNotice(Notice.cantCheck)
                return
            }
        }
    }

    /// API-CONTRACT §1.1: 503 / 504 / 500 are retried once after 1 s for `/check`.
    static func isRetriedOnce(_ error: APIError) -> Bool {
        guard let status = error.status else { return false }
        return [500, 503, 504].contains(status)
    }

    /// Stale-result rule (§3.4): the latest request for the step on screen, or nothing.
    private func isLatest(_ requestID: String, stepID: String) -> Bool {
        latestCheckRequestID?.lowercased() == requestID.lowercased() && currentStep?.id == stepID
    }

    private func apply(_ response: CheckResponse) {
        // Echoed ids decide; a response for another request or step is dropped silently.
        guard let stepID = currentStep?.id,
            response.stepID.lowercased() == stepID.lowercased(),
            isLatest(response.requestID, stepID: stepID),
            let card = currentCard()
        else { return }
        latestCheckRequestID = nil
        lastCheck = response
        watcher.noteNetwork(reachable: true)

        switch response.verdict {
        case .pass:
            let screen = LensScreen.pass(headline: response.headline.isEmpty ? "Looks right" : response.headline)
            lens = screen
            speech.playChime()
            speak(response.spoken, fallback: screen)
            schedule(after: Timing.passAutoAdvance) { session in
                session.advance(via: .auto)
            }
        case .fix:
            let screen = LensScreen.fix(
                card, headline: response.headline.isEmpty ? "Not quite" : response.headline,
                fix: response.fix, proactive: false)
            lens = screen
            speak(response.spoken, fallback: screen)
        case .unsure, .unknown:
            let screen = LensScreen.unsure(
                headline: response.headline.isEmpty ? "Can't tell" : response.headline,
                hint: response.fix)
            lens = screen
            speak(response.spoken, fallback: screen)
            schedule(after: Timing.unsureReturn) { session in
                session.showStep()
            }
        }
    }

    private func showNotice(_ text: String) {
        latestCheckRequestID = nil
        lens = .notice(text)
        speech.speak(text, priority: .result)
        schedule(after: Timing.noticeReturn) { session in
            session.showStep()
        }
    }

    // MARK: Navigation

    private func advance(via: InputVia) {
        guard let recipe else { return }
        if stepIndex + 1 >= recipe.steps.count {
            finish()
        } else {
            goToStep(stepIndex + 1, via: via)
        }
    }

    private func goToStep(_ index: Int, via: InputVia) {
        guard let recipe, recipe.steps.indices.contains(index) else { return }
        let from = stepIndex
        cancelTimers()
        stepIndex = index
        activeWarningID = nil
        watcher.stepDidChange()
        showStep()
        if index != from {
            postEvent(
                .stepChange, stepID: recipe.steps[index].id,
                payload: [
                    "from_idx": .number(Double(recipe.steps[from].idx)),
                    "to_idx": .number(Double(recipe.steps[index].idx)),
                    "via": .string(via.rawValue),
                ])
        }
        // A manual change makes whatever was being said stale; after an auto-advance the pass
        // sentence finishes first and the step is queued behind it.
        if via != .auto { speech.stop() }
        speakLens(priority: .info)
        if index != from { voice?.stepDidChange() }
    }

    private func finish() {
        cancelTimers()
        activeWarningID = nil
        watcher.stop()
        lens = .done(nil)
        guard let sessionID, !sessionEnded else {
            speakLens(priority: .info)
            return
        }
        sessionEnded = true
        let api = api
        screenTimer = Task { [weak self] in
            do {
                try await api.postEvent(
                    sessionID: sessionID, kind: .sessionEnd, stepID: nil, requestID: nil, payload: [:])
            } catch {
                self?.log("session_end failed: \(error.localizedDescription)")
            }
            let summary = try? await api.session(id: sessionID).summary
            guard let self, !Task.isCancelled, self.isDone else { return }
            self.lens = .done(summary)
            self.speakLens(priority: .info)
        }
    }

    /// Back to the plain step card for the current step; invalidates any pending check.
    private func showStep() {
        cancelTimers()
        if let card = currentCard() { lens = .step(card) }
    }

    private func currentCard() -> StepCard? {
        guard let recipe, let step = currentStep else { return nil }
        return StepCard(
            idx: step.idx, total: recipe.steps.count, title: step.title, keyLine: step.keyLine,
            refImage: cache.imageRef(stepID: step.id), watching: watchIndicator)
    }

    // MARK: Watcher (IOS-04)

    /// App moved to / from the background (a watcher pause condition).
    func setAppActive(_ active: Bool) {
        guard active != isAppActive else { return }
        isAppActive = active
        watcher.stateDidChange()
    }

    /// Gemini Live is listening or answering (IOS-05 calls this; a watcher pause condition).
    func setTalking(_ talking: Bool) {
        guard talking != isTalking else { return }
        isTalking = talking
        watcher.stateDidChange()
    }

    /// Watcher on/off, threshold or interval changed in Settings: applies on the next tick.
    func watcherSettingsDidChange() {
        watcher.stateDidChange()
    }

    /// The watcher sends only while the plain step card is showing (API-CONTRACT §3.3).
    var watchGate: WatchGate {
        guard phase == .cooking, let step = currentStep, !isDone else { return .inactive }
        guard !step.watchFors.isEmpty else { return .off }
        guard case .step = lens, latestCheckRequestID == nil, isAppActive, !isTalking else { return .paused }
        return .open(stepID: step.id, sessionID: sessionID)
    }

    func watcher(didChangeIndicator indicator: WatchIndicator) {
        watchIndicator = indicator
        // Only the plain step card is redrawn: other screens may have a timer keyed to their value.
        if case .step(let card) = lens, card.watching != indicator {
            lens = .step(card.with(watching: indicator))
        }
    }

    func watcher(didAlert response: WatchResponse) {
        guard case .step = lens, let step = currentStep,
            response.stepID.lowercased() == step.id.lowercased(),
            let mistakeID = response.mistakeID, let card = currentCard()
        else { return }
        // Fill in from the step's own watch-for if the server left a string empty.
        let known = step.watchFors.first { $0.id == mistakeID }
        let headline = response.headline.isEmpty ? (known?.headline ?? "Watch out") : response.headline
        let fix = response.fix.isEmpty ? (known?.fix ?? "") : response.fix
        let spoken = response.spoken.isEmpty ? (known?.spoken ?? "") : response.spoken
        cancelTimers()
        activeWarningID = mistakeID
        let screen = LensScreen.fix(card, headline: headline, fix: fix, proactive: true)
        lens = screen
        speak(spoken, fallback: screen)
        postEvent(.warningShown, stepID: step.id, payload: ["mistake_id": .string(mistakeID)])
        schedule(after: Timing.warningAutoDismiss) { session in
            session.dismissWarning()
        }
    }

    /// `dismiss` on a proactive warning, or 12 s without input: back to the step, mute the id.
    private func dismissWarning() {
        guard case .fix(_, _, _, true) = lens, let mistakeID = activeWarningID else { return }
        activeWarningID = nil
        watcher.dismissed(mistakeID: mistakeID)
        postEvent(.warningDismissed, stepID: currentStep?.id, payload: ["mistake_id": .string(mistakeID)])
        showStep()
    }

    // MARK: Helpers

    /// Cancels the screen timer and any pending check; the pending request id stops being valid.
    private func cancelTimers() {
        screenTimer?.cancel()
        screenTimer = nil
        pendingCheck?.cancel()
        pendingCheck = nil
        latestCheckRequestID = nil
    }

    private func schedule(after delay: Duration, _ action: @escaping @MainActor (CookSession) -> Void) {
        screenTimer?.cancel()
        let clock = clock
        let screen = lens
        screenTimer = Task { [weak self] in
            do { try await clock.sleep(for: delay) } catch { return }
            // Only fire if nothing changed the screen meanwhile.
            guard let self, !Task.isCancelled, self.lens == screen else { return }
            action(self)
        }
    }

    private func speak(_ spoken: String, fallback: LensScreen) {
        let text = spoken.isEmpty ? (fallback.spokenText ?? "") : spoken
        speech.speak(text, priority: .result)
    }

    private func speakLens(priority: SpeechPriority) {
        if let text = lens.spokenText { speech.speak(text, priority: priority) }
    }

    /// Fire-and-forget: a failed event post is logged and never blocks the UI.
    private func postEvent(
        _ kind: SessionEventKind, stepID: String?, payload: [String: JSONValue] = [:]
    ) {
        guard let sessionID else { return }
        let api = api
        Task { [weak self] in
            do {
                try await api.postEvent(
                    sessionID: sessionID, kind: kind, stepID: stepID, requestID: nil, payload: payload)
            } catch {
                self?.log("event \(kind.rawValue) failed: \(error.localizedDescription)")
            }
        }
    }

    private func endSessionInBackground() {
        guard sessionID != nil, !sessionEnded else { return }
        sessionEnded = true
        postEvent(.sessionEnd, stepID: nil)
    }

    private func log(_ message: String) {
        print("[cook] \(message)")
    }
}

// MARK: - Gemini Live (IOS-05.4, 05.5)

extension CookSession: VoiceHost {
    var voiceRecipeID: String? { recipe?.id }
    var voiceSessionID: String? { sessionID }

    var voiceStep: VoiceStepContext? {
        guard let recipe, let step = currentStep else { return nil }
        return VoiceStepContext(
            idx: step.idx, total: recipe.steps.count, title: step.title,
            instruction: step.instruction.isEmpty ? step.keyLine : step.instruction)
    }

    /// Listening / answering on the lens. The watcher pauses through `isTalking`.
    func voiceShowTalking(_ phase: TalkPhase, caption: String) {
        guard self.phase == .cooking, !isDone else { return }
        if case .talking = lens {
        } else {
            lensBeforeTalking = lens
        }
        setTalking(true)
        lens = .talking(phase: phase, caption: caption)
    }

    /// Back to the screen before the turn. Transient screens (pass, unsure, notice) whose timers
    /// were skipped while talking go back to the step instead; a pass still advances.
    func voiceEndTalking() {
        let previous = lensBeforeTalking
        lensBeforeTalking = nil
        setTalking(false)
        // A verdict or a step change replaced the talking screen meanwhile: leave it.
        guard case .talking = lens else { return }
        switch previous {
        case .fix(let card, let headline, let fix, let proactive)?:
            lens = .fix(currentCard() ?? card, headline: headline, fix: fix, proactive: proactive)
            if proactive {
                schedule(after: Timing.warningAutoDismiss) { session in session.dismissWarning() }
            }
        case .showMe?:
            if let card = currentCard() { lens = .showMe(card) } else { showStep() }
        case .checking?:
            // The check may still be in flight; its verdict replaces this when it lands.
            if latestCheckRequestID != nil, let card = currentCard() { lens = .checking(card) } else { showStep() }
        case .pass?:
            advance(via: .auto)
        default:
            showStep()
        }
    }

    /// A voice command takes the gesture's path with `via: voice`. `check_my_work` checks from a
    /// step, fix or talking screen; it never advances a pass.
    func voiceRun(_ input: CookInput) {
        if input == .primary, case .pass = lens { return }
        send(input, via: .voice)
    }

    func voicePostQuestion(caption: String, transcript: String) {
        var payload: [String: JSONValue] = ["caption": .string(caption)]
        if !transcript.isEmpty { payload["transcript"] = .string(transcript) }
        postEvent(.question, stepID: currentStep?.id, payload: payload)
    }

    func voicePostClientError(_ detail: String) {
        postEvent(.clientError, stepID: currentStep?.id, payload: ["where": .string("live"), "detail": .string(detail)])
    }
}
