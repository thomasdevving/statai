import Foundation
import Observation

// Gemini Live inside a cook-along (IOS-05.4 – 05.7).
// Fetches `/live-token`, opens the socket in the background, sends the step context, streams the
// mic, plays answers, runs voice commands, and reconnects. Any failure means "voice unavailable"
// (a crossed-mic badge); it never shows a dialog and never blocks the rest of the app.

/// The step the cook is on, as Live needs it.
struct VoiceStepContext: Equatable, Sendable {
    let idx: Int
    let total: Int
    let title: String
    let instruction: String
}

/// What the controller needs from the cook-along. `CookSession` conforms.
@MainActor
protocol VoiceHost: AnyObject {
    var voiceRecipeID: String? { get }
    var voiceSessionID: String? { get }
    var voiceStep: VoiceStepContext? { get }
    /// Show `.talking(phase, caption)` on the lens and pause the watcher.
    func voiceShowTalking(_ phase: TalkPhase, caption: String)
    /// Back to the screen before talking; the watcher resumes.
    func voiceEndTalking()
    /// A voice command runs the same path as the gesture (`via: voice`).
    func voiceRun(_ input: CookInput)
    func voicePostQuestion(caption: String, transcript: String)
    func voicePostClientError(_ detail: String)
}

enum VoiceStatus: Equatable, Sendable {
    case off
    case connecting
    case ready
    /// Voice is down; the reason is for the Voice Lab log only.
    case unavailable(String)
    /// Microphone permission denied: voice off, everything else works.
    case micDenied
}

@MainActor
@Observable
final class VoiceController: LivePlaybackControl {
    private(set) var status: VoiceStatus = .off
    /// The Voice Lab's event log (newest last, capped).
    private(set) var log: [String] = []
    /// What the cook said in the current or last turn, and the model's caption.
    private(set) var inputText = ""
    private(set) var outputText = ""
    var micMode: VoiceMicMode = .openMic {
        didSet { if micMode != oldValue, micMode == .pushToTalk { pushToTalkHeld = false } }
    }
    /// Push-to-talk button state. Releasing it tells the server the mic stopped.
    var pushToTalkHeld = false {
        didSet {
            guard oldValue, !pushToTalkHeld, micMode == .pushToTalk else { return }
            send(LiveOutgoing.audioStreamEnd())
        }
    }

    weak var host: (any VoiceHost)?

    @ObservationIgnored private let api: any GhostChefAPI
    @ObservationIgnored private let connector: any LiveConnecting
    @ObservationIgnored private let audio: (any LiveAudio)?
    @ObservationIgnored private let clock: any CookClock
    @ObservationIgnored private let ttsIsSpeaking: @MainActor () -> Bool
    @ObservationIgnored private let requestMicPermission: @MainActor () async -> Bool

    @ObservationIgnored private var connection: (any LiveConnection)?
    @ObservationIgnored private var token: LiveTokenResponse?
    @ObservationIgnored private var resumeHandle: String?
    @ObservationIgnored private var connectTask: Task<Void, Never>?
    @ObservationIgnored private var eventsTask: Task<Void, Never>?
    @ObservationIgnored private var outbox: AsyncStream<Data>.Continuation?
    @ObservationIgnored private var outboxTask: Task<Void, Never>?
    @ObservationIgnored private var micTask: Task<Void, Never>?
    @ObservationIgnored private var micContinuation: AsyncStream<Data>.Continuation?
    @ObservationIgnored private var stopped = true

    // Turn state.
    @ObservationIgnored private var turnHasAudio = false
    @ObservationIgnored private var turnComplete = false
    @ObservationIgnored private var lastWasToolCall = false
    @ObservationIgnored private var dropRestOfTurn = false
    @ObservationIgnored private var showing: TalkPhase?
    @ObservationIgnored private var shownCaption = ""

    init(
        api: any GhostChefAPI, connector: any LiveConnecting = LiveClient(), audio: (any LiveAudio)?,
        clock: any CookClock = SystemCookClock(), ttsIsSpeaking: @escaping @MainActor () -> Bool,
        requestMicPermission: @escaping @MainActor () async -> Bool = { await MicPermission.request() }
    ) {
        self.api = api
        self.connector = connector
        self.audio = audio
        self.clock = clock
        self.ttsIsSpeaking = ttsIsSpeaking
        self.requestMicPermission = requestMicPermission
        audio?.onPlaybackDrained = { [weak self] in self?.playbackDrained() }
    }

    var isConnected: Bool { connection != nil }

    // MARK: Lifecycle

    /// Called once the first step card is up. Connects in the background.
    func start() {
        stopped = false
        connectFresh()
    }

    func stop() {
        stopped = true
        connectTask?.cancel()
        tearDownConnection()
        audio?.stop()
        endTurn(postQuestion: false)
        token = nil
        resumeHandle = nil
        status = .off
    }

    /// On every step change: tell the model where the cook is, or retry a failed connection
    /// with a new token.
    func stepDidChange() {
        guard !stopped else { return }
        if connection != nil {
            sendContext()
        } else if connectTask == nil {
            connectFresh()
        }
    }

    // MARK: Voice Lab

    /// A typed question from Settings → Voice Lab.
    func sendTypedQuestion(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        note("→ text: \(trimmed)")
        send(LiveOutgoing.text(trimmed, turnComplete: !trimmed.hasPrefix("[CONTEXT]")))
    }

    // MARK: LivePlaybackControl (the arbiter)

    var isLiveAnswering: Bool { turnHasAudio && !dropRestOfTurn }

    /// A check verdict or warning needs the speaker: cut the answer and leave the talking screen.
    func stopLivePlayback() {
        audio?.flushPlayback()
        guard turnHasAudio else { return }
        // If the server is still streaming this answer, drop the rest of it until its
        // turnComplete; if it already finished, the next turn must play normally.
        let stillStreaming = !turnComplete
        endTurn(postQuestion: true)
        dropRestOfTurn = stillStreaming
    }

    // MARK: Connecting

    private func connectFresh() {
        connectTask?.cancel()
        status = .connecting
        connectTask = Task { [weak self] in
            await self?.connect(plan: .newToken(handle: nil), isRetry: false)
            self?.connectTask = nil
        }
    }

    /// One connection attempt. Returns true on success.
    @discardableResult
    private func connect(plan: LiveReconnect.Plan, isRetry: Bool) async -> Bool {
        guard let recipeID = host?.voiceRecipeID else {
            status = .unavailable("No recipe")
            return false
        }
        do {
            let useToken: LiveTokenResponse
            let handle: String?
            switch plan {
            case .resumeWithSameToken(let h):
                guard let token else { throw LiveClientError.closed }
                useToken = token
                handle = h
            case .newToken(let h):
                useToken = try await api.liveToken(recipeID: recipeID, sessionID: host?.voiceSessionID)
                handle = h
            }
            guard !Task.isCancelled, !stopped else { return false }
            let conn = try await connector.connect(token: useToken, resumeHandle: handle)
            guard !Task.isCancelled, !stopped else {
                conn.close()
                return false
            }
            token = useToken
            attach(conn)
            note(handle == nil ? "connected (\(useToken.model))" : "resumed")
            status = .ready
            sendContext()
            await startMicIfAllowed()
            return true
        } catch is CancellationError {
            return false
        } catch {
            note("connect failed: \(error.localizedDescription)")
            if !isRetry { status = .unavailable(error.localizedDescription) }
            return false
        }
    }

    private func attach(_ conn: any LiveConnection) {
        connection = conn
        let (stream, continuation) = AsyncStream.makeStream(of: Data.self, bufferingPolicy: .unbounded)
        outbox = continuation
        outboxTask = Task {
            for await message in stream {
                do { try await conn.send(message) } catch { /* the events stream reports the close */ }
            }
        }
        eventsTask?.cancel()
        eventsTask = Task { [weak self] in
            for await event in conn.events {
                guard let self, !Task.isCancelled else { return }
                self.handle(event)
            }
            // The stream ended: the socket closed. Ours (stop / reconnect) or the server's.
            guard let self, !Task.isCancelled, self.connection === conn else { return }
            self.connectionLost("socket closed")
        }
    }

    private func tearDownConnection() {
        eventsTask?.cancel()
        eventsTask = nil
        outbox?.finish()
        outbox = nil
        outboxTask?.cancel()
        outboxTask = nil
        connection?.close()
        connection = nil
        audio?.stopMic()
        micContinuation?.finish()
        micContinuation = nil
        micTask?.cancel()
        micTask = nil
    }

    /// IOS-05.7: reconnect with the handle (same token while valid, else a new one), backing off
    /// 1 s, 2 s, 5 s; then voice stays unavailable until the next step change.
    private func connectionLost(_ reason: String) {
        guard !stopped else { return }
        note("lost: \(reason)")
        tearDownConnection()
        audio?.flushPlayback()
        endTurn(postQuestion: false)
        host?.voicePostClientError(reason)
        status = .connecting
        connectTask?.cancel()
        connectTask = Task { [weak self] in
            var attempt = 0
            while let delay = LiveReconnect.delay(beforeAttempt: attempt) {
                guard let self else { return }
                do { try await self.clock.sleep(for: delay) } catch { return }
                let plan = LiveReconnect.plan(token: self.token, handle: self.resumeHandle, now: self.clock.now)
                if await self.connect(plan: plan, isRetry: true) {
                    self.connectTask = nil
                    return
                }
                attempt += 1
            }
            guard let self else { return }
            self.status = .unavailable("Voice offline")
            self.connectTask = nil
        }
    }

    // MARK: Mic

    private func startMicIfAllowed() async {
        guard let audio else { return }
        guard await requestMicPermission() else {
            status = .micDenied
            note("microphone permission denied")
            return
        }
        do {
            try audio.start()
            let (stream, continuation) = AsyncStream.makeStream(of: Data.self, bufferingPolicy: .bufferingNewest(20))
            micContinuation = continuation
            // Chunks come from the audio thread; one consumer keeps them in order.
            micTask = Task { [weak self] in
                for await chunk in stream {
                    self?.micChunk(chunk)
                }
            }
            try audio.startMic { chunk in continuation.yield(chunk) }
        } catch {
            note("audio failed: \(error.localizedDescription)")
            status = .unavailable("Audio unavailable")
        }
    }

    private func micChunk(_ chunk: Data) {
        guard connection != nil,
            VoiceArbiter.shouldSendMic(mode: micMode, pushToTalkHeld: pushToTalkHeld, ttsSpeaking: ttsIsSpeaking())
        else { return }
        send(LiveOutgoing.audio(chunk))
    }

    // MARK: Events

    func handle(_ event: LiveServerEvent) {
        switch event {
        case .setupComplete, .generationComplete:
            break

        case .audio(let pcm):
            lastWasToolCall = false
            guard !dropRestOfTurn else { return }
            // Our own TTS has the speaker: Live audio that arrives meanwhile is dropped (§5.3).
            if ttsIsSpeaking() { return }
            if !turnHasAudio {
                turnHasAudio = true
                note("← answer audio")
            }
            show(.answering, caption: LiveCaption.lensCaption(from: outputText))
            audio?.enqueuePlayback(pcm)

        case .outputTranscript(let piece):
            outputText += piece
            if turnHasAudio, !dropRestOfTurn {
                show(.answering, caption: LiveCaption.lensCaption(from: outputText))
            }

        case .inputTranscript(let piece):
            inputText += piece
            if !turnHasAudio { show(.listening, caption: "") }

        case .voiceActivityStart:
            if !turnHasAudio { show(.listening, caption: "") }

        case .voiceActivityEnd:
            break

        case .interrupted:
            // Barge-in: stop at once, drop queued audio; the cook's new turn follows.
            note("← interrupted")
            audio?.flushPlayback()
            turnHasAudio = false
            outputText = ""
            show(.listening, caption: "")

        case .toolCall(let calls):
            lastWasToolCall = true
            runToolCalls(calls)

        case .toolCallCancellation(let ids):
            note("← tool calls cancelled: \(ids.joined(separator: ", "))")

        case .turnComplete:
            // The turnComplete right after a toolCall is not an answer (AI-05 notes).
            if lastWasToolCall, !turnHasAudio {
                lastWasToolCall = false
                // Still release the talking screen, or the watcher would stay paused.
                endTurn(postQuestion: false)
                return
            }
            lastWasToolCall = false
            note("← turn complete")
            if turnHasAudio, audio?.isPlayingLiveAudio == true, !dropRestOfTurn {
                turnComplete = true  // finish when the queued audio has played
            } else {
                endTurn(postQuestion: turnHasAudio && !dropRestOfTurn)
            }

        case .resumptionUpdate(let handle, let resumable):
            if resumable { resumeHandle = handle }

        case .goAway(let timeLeft):
            note("← go away (\(timeLeft ?? "?"))")
            connectionLost("go away")
        }
    }

    /// IOS-05.5: run each call through the gesture path and answer at once (never leave a call
    /// unanswered; for a check the answer does not wait for the verdict).
    private func runToolCalls(_ calls: [LiveFunctionCall]) {
        var responses: [LiveToolResponse] = []
        for call in calls {
            let command = VoiceCommand(functionName: call.name)
            note("← \(call.name)")
            if let input = command.input { host?.voiceRun(input) }
            let step = host?.voiceStep
            let nowOn = step.map { VoiceCommandResponses.nowOn(stepIdx: $0.idx, total: $0.total, title: $0.title) } ?? ""
            responses.append(VoiceCommandResponses.response(for: call, nowOn: nowOn, instruction: step?.instruction ?? ""))
        }
        send(LiveOutgoing.toolResponse(responses))
    }

    private func playbackDrained() {
        guard turnComplete else { return }
        endTurn(postQuestion: !dropRestOfTurn)
    }

    // MARK: Turn helpers

    private func show(_ phase: TalkPhase, caption: String) {
        guard showing != phase || shownCaption != caption else { return }
        showing = phase
        shownCaption = caption
        host?.voiceShowTalking(phase, caption: caption)
    }

    private func endTurn(postQuestion: Bool) {
        if postQuestion {
            let caption = LiveCaption.lensCaption(from: outputText)
            host?.voicePostQuestion(caption: caption, transcript: LiveCaption.clean(inputText))
        }
        if showing != nil { host?.voiceEndTalking() }
        resetTurn()
    }

    private func resetTurn() {
        turnHasAudio = false
        turnComplete = false
        dropRestOfTurn = false
        showing = nil
        shownCaption = ""
        inputText = ""
        outputText = ""
    }

    private func sendContext() {
        guard let step = host?.voiceStep else { return }
        send(LiveOutgoing.text(liveContextLine(stepIdx: step.idx, total: step.total, title: step.title), turnComplete: false))
    }

    /// Queues a message on the current connection's outbox; one sender keeps wire order (audio
    /// chunks, context lines and tool responses must not overtake each other).
    private func send(_ message: Data) {
        guard connection != nil else { return }
        outbox?.yield(message)
    }

    private func note(_ line: String) {
        log.append(line)
        if log.count > 100 { log.removeFirst(log.count - 100) }
    }
}
