import Foundation
import Testing

@testable import GhostChef

// IOS-05: Gemini Live voice. Wire shapes are checked against the literal JSON in
// ai/STATUS.md → "Live facts for ios/". Audio itself is verified by ear on a device.

/// Parses JSON so encoded messages compare structurally, not by key order.
private func json(_ data: Data) -> JSONValue? {
    try? JSONDecoder().decode(JSONValue.self, from: data)
}

private func json(_ text: String) -> JSONValue? {
    json(Data(text.utf8))
}

private func liveToken(locked: Bool = true, expiresIn: TimeInterval = 1800, token: String = "auth_tokens/abc") -> LiveTokenResponse {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    return LiveTokenResponse(
        token: token, expiresAt: now.addingTimeInterval(expiresIn), newSessionExpiresAt: now.addingTimeInterval(60),
        model: "gemini-3.8-live", apiVersion: "v1beta", locked: locked,
        config: LiveConfig(
            systemInstruction: "You are the chef.", responseModalities: ["AUDIO"], voice: nil,
            tools: [.object(["function_declarations": .array([.object(["name": .string("next_step"), "behavior": .string("NON_BLOCKING")])])])],
            sessionResumption: true))
}

// MARK: - Wire protocol

@Suite("Live protocol")
struct LiveProtocolTests {
    @Test func endpointUsesConstrainedV1betaAndTokenHeader() {
        let request = LiveEndpoint.request(token: "auth_tokens/xyz")
        #expect(request.url?.absoluteString == "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Token auth_tokens/xyz")
    }

    @Test func modelPathAddsPrefixOnce() {
        #expect(LiveEndpoint.modelPath("gemini-3.8-live") == "models/gemini-3.8-live")
        #expect(LiveEndpoint.modelPath("models/gemini-3.8-live") == "models/gemini-3.8-live")
    }

    @Test func lockedSetupSendsOnlyModelAndEmptyResumption() {
        let data = LiveOutgoing.setup(token: liveToken(), resumeHandle: nil)
        #expect(json(data) == json(#"{"setup":{"model":"models/gemini-3.8-live","sessionResumption":{}}}"#))
    }

    @Test func resumeSetupCarriesTheHandle() {
        let data = LiveOutgoing.setup(token: liveToken(), resumeHandle: "h-1")
        #expect(json(data) == json(#"{"setup":{"model":"models/gemini-3.8-live","sessionResumption":{"handle":"h-1"}}}"#))
    }

    @Test func unlockedSetupSendsConfigWithCamelCaseTools() throws {
        let data = LiveOutgoing.setup(token: liveToken(locked: false), resumeHandle: nil)
        let expected = json(#"""
            {"setup":{"model":"models/gemini-3.8-live","generationConfig":{"responseModalities":["AUDIO"]},
            "systemInstruction":{"parts":[{"text":"You are the chef."}],"role":"user"},
            "tools":[{"functionDeclarations":[{"name":"next_step","behavior":"NON_BLOCKING"}]}],
            "sessionResumption":{},"inputAudioTranscription":{},"outputAudioTranscription":{},
            "contextWindowCompression":{"slidingWindow":{}}}}
            """#)
        #expect(json(data) == expected)
    }

    @Test func contextLineIsSentWithTurnCompleteFalse() {
        let line = liveContextLine(stepIdx: 4, total: 6, title: "Add fillings")
        #expect(line == #"[CONTEXT] Cook is now on step 4 of 6: "Add fillings". Do not reply to this message."#)
        let data = LiveOutgoing.text(line, turnComplete: false)
        let expected = JSONValue.object([
            "clientContent": .object([
                "turns": .array([.object(["role": .string("user"), "parts": .array([.object(["text": .string(line)])])])]),
                "turnComplete": .bool(false),
            ])
        ])
        #expect(json(data) == expected)
    }

    @Test func typedQuestionCompletesTheTurn() {
        let data = LiveOutgoing.text("Why spread to the edges?", turnComplete: true)
        #expect(json(data) == json(#"{"clientContent":{"turns":[{"role":"user","parts":[{"text":"Why spread to the edges?"}]}],"turnComplete":true}}"#))
    }

    @Test func audioChunkIsBase64Pcm16k() {
        let pcm = Data([0x01, 0x02, 0x03, 0x04])
        let data = LiveOutgoing.audio(pcm)
        #expect(json(data) == json(#"{"realtimeInput":{"audio":{"data":"AQIDBA==","mimeType":"audio/pcm;rate=16000"}}}"#))
        #expect(LiveAudioFormat.inputChunkBytes == 3_200)
    }

    @Test func audioStreamEnd() {
        #expect(json(LiveOutgoing.audioStreamEnd()) == json(#"{"realtimeInput":{"audioStreamEnd":true}}"#))
    }

    @Test func toolResponseSilentOnlyWhenAsked() {
        let data = LiveOutgoing.toolResponse([
            LiveToolResponse(id: "c1", name: "next_step", response: ["status": .string("done"), "now_on": .string("5 of 6: Close")], silent: true),
            LiveToolResponse(id: "c2", name: "repeat_instruction", response: ["instruction": .string("Spread to the crust.")], silent: false),
        ])
        let expected = json(#"""
            {"toolResponse":{"functionResponses":[
            {"id":"c1","name":"next_step","response":{"status":"done","now_on":"5 of 6: Close"},"scheduling":"SILENT"},
            {"id":"c2","name":"repeat_instruction","response":{"instruction":"Spread to the crust."}}]}}
            """#)
        #expect(json(data) == expected)
    }

    // MARK: Incoming (literal shapes from the AI-05 run)

    @Test func decodesSetupComplete() {
        #expect(LiveIncoming.decode(Data(#"{"setupComplete":{}}"#.utf8)) == [.setupComplete])
    }

    @Test func decodesAudioChunkAndCaptionInOneFrame() {
        let frame = #"""
            {"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":"AAEC"}}]},
            "outputTranscription":{"text":"So every bite "}}}
            """#
        #expect(LiveIncoming.decode(Data(frame.utf8)) == [.audio(Data([0x00, 0x01, 0x02])), .outputTranscript("So every bite ")])
    }

    @Test func decodesInputTranscriptionAndTurnEnd() {
        #expect(LiveIncoming.decode(Data(#"{"serverContent":{"inputTranscription":{"text":"why the edges"}}}"#.utf8)) == [.inputTranscript("why the edges")])
        let end = #"{"serverContent":{"generationComplete":true,"turnComplete":true},"usageMetadata":{"totalTokenCount":12}}"#
        #expect(LiveIncoming.decode(Data(end.utf8)) == [.generationComplete, .turnComplete])
    }

    @Test func decodesToolCall() {
        let frame = #"{"toolCall":{"functionCalls":[{"name":"check_my_work","args":{},"id":"call_9877"}]}}"#
        #expect(LiveIncoming.decode(Data(frame.utf8)) == [.toolCall([LiveFunctionCall(id: "call_9877", name: "check_my_work", args: [:])])])
    }

    @Test func decodesResumptionGoAwayActivityAndInterrupt() {
        #expect(LiveIncoming.decode(Data(#"{"sessionResumptionUpdate":{"newHandle":"h-9","resumable":true}}"#.utf8)) == [.resumptionUpdate(handle: "h-9", resumable: true)])
        #expect(LiveIncoming.decode(Data(#"{"goAway":{"timeLeft":"10s"}}"#.utf8)) == [.goAway(timeLeft: "10s")])
        #expect(LiveIncoming.decode(Data(#"{"voiceActivity":{"type":"ACTIVITY_START","audioOffset":"0.240s"}}"#.utf8)) == [.voiceActivityStart])
        #expect(LiveIncoming.decode(Data(#"{"serverContent":{"interrupted":true}}"#.utf8)) == [.interrupted])
        #expect(LiveIncoming.decode(Data(#"{"toolCallCancellation":{"ids":["a","b"]}}"#.utf8)) == [.toolCallCancellation(["a", "b"])])
    }

    @Test func ignoresEmptyAndGarbage() {
        #expect(LiveIncoming.decode(Data(#"{"serverContent":{}}"#.utf8)).isEmpty)
        #expect(LiveIncoming.decode(Data("not json".utf8)).isEmpty)
    }

    @Test func captionsHideNonSpeechMarkersAndKeepFiveWords() {
        #expect(LiveCaption.clean("<no speech detected> So every {pause} bite") == "So every bite")
        #expect(LiveCaption.lensCaption(from: "") == "Answering…")
        #expect(LiveCaption.lensCaption(from: "<no speech>") == "Answering…")
        #expect(LiveCaption.lensCaption(from: "Edges stay soft") == "Edges stay soft")
        #expect(LiveCaption.lensCaption(from: "So every bite has filling in it") == "So every bite has filling…")
    }
}

// MARK: - Commands, arbiter, reconnect

@Suite("Voice commands")
struct VoiceCommandTests {
    private func call(_ name: String) -> LiveFunctionCall { LiveFunctionCall(id: "id-\(name)", name: name, args: [:]) }

    @Test func namesMapToGesturePaths() {
        #expect(VoiceCommand(functionName: "check_my_work").input == .primary)
        #expect(VoiceCommand(functionName: "next_step").input == .next)
        #expect(VoiceCommand(functionName: "previous_step").input == .previous)
        #expect(VoiceCommand(functionName: "show_me").input == .showMe)
        #expect(VoiceCommand(functionName: "repeat_instruction").input == nil)
        #expect(VoiceCommand(functionName: "dance") == .unknown("dance"))
    }

    @Test func responsesFollowTheContractTable() {
        let check = VoiceCommandResponses.response(for: call("check_my_work"), nowOn: "4 of 6: Add fillings", instruction: "x")
        #expect(check.response == ["status": .string("done"), "note": .string("The app has shown and spoken the result. Say nothing more.")])
        #expect(check.silent)
        let next = VoiceCommandResponses.response(for: call("next_step"), nowOn: "5 of 6: Close", instruction: "x")
        #expect(next.response == ["status": .string("done"), "now_on": .string("5 of 6: Close")])
        #expect(next.silent && next.id == "id-next_step" && next.name == "next_step")
        #expect(VoiceCommandResponses.response(for: call("show_me"), nowOn: "", instruction: "").response == ["status": .string("done")])
        let again = VoiceCommandResponses.response(for: call("repeat_instruction"), nowOn: "", instruction: "Spread to the crust.")
        #expect(again.response == ["instruction": .string("Spread to the crust.")])
        #expect(!again.silent, "the model must read the instruction aloud")
        let unknown = VoiceCommandResponses.response(for: call("dance"), nowOn: "", instruction: "")
        #expect(unknown.response["error"] != nil)
    }

    @Test func nowOnFormat() {
        #expect(VoiceCommandResponses.nowOn(stepIdx: 5, total: 6, title: "Close") == "5 of 6: Close")
    }
}

@Suite("Voice arbiter")
struct VoiceArbiterTests {
    @Test func resultsWinAndInfoWaits() {
        #expect(VoiceArbiter.onResult(liveAnswering: true) == .stopLiveThenSpeak)
        #expect(VoiceArbiter.onResult(liveAnswering: false) == .speak)
        #expect(!VoiceArbiter.allowsInfo(liveAnswering: true))
        #expect(VoiceArbiter.allowsInfo(liveAnswering: false))
    }

    @Test func micIsGatedByTtsAndPushToTalk() {
        #expect(VoiceArbiter.shouldSendMic(mode: .openMic, pushToTalkHeld: false, ttsSpeaking: false))
        #expect(!VoiceArbiter.shouldSendMic(mode: .openMic, pushToTalkHeld: false, ttsSpeaking: true))
        #expect(!VoiceArbiter.shouldSendMic(mode: .pushToTalk, pushToTalkHeld: false, ttsSpeaking: false))
        #expect(VoiceArbiter.shouldSendMic(mode: .pushToTalk, pushToTalkHeld: true, ttsSpeaking: false))
        #expect(!VoiceArbiter.shouldSendMic(mode: .pushToTalk, pushToTalkHeld: true, ttsSpeaking: true))
    }

    @MainActor @Test func arbitratedSpeechStopsLiveForResultsAndSkipsInfo() {
        let base = FakeSpeech()
        let live = FakePlayback()
        let speech = ArbitratedSpeech(base: base)
        speech.live = live

        live.isLiveAnswering = true
        speech.speak("Step 5 of 6.", priority: .info)
        #expect(base.spoken.isEmpty, "step read-outs are skipped while Live answers")
        speech.speak("Filling piled up.", priority: .result)
        #expect(live.stops == 1)
        #expect(base.texts == ["Filling piled up."])

        live.isLiveAnswering = false
        speech.speak("Step 5 of 6.", priority: .info)
        #expect(base.texts == ["Filling piled up.", "Step 5 of 6."])
        #expect(live.stops == 1)
    }
}

@Suite("Live reconnect")
struct LiveReconnectTests {
    let now = Date(timeIntervalSince1970: 1_800_000_000)

    @Test func reusesTheTokenWithAHandleWhileValid() {
        #expect(LiveReconnect.plan(token: liveToken(expiresIn: 600), handle: "h", now: now) == .resumeWithSameToken(handle: "h"))
    }

    @Test func newTokenWhenExpiringOrNoHandle() {
        #expect(LiveReconnect.plan(token: liveToken(expiresIn: 10), handle: "h", now: now) == .newToken(handle: "h"))
        #expect(LiveReconnect.plan(token: liveToken(), handle: nil, now: now) == .newToken(handle: nil))
        #expect(LiveReconnect.plan(token: nil, handle: "h", now: now) == .newToken(handle: "h"))
    }

    @Test func backsOffOneTwoFiveThenGivesUp() {
        #expect(LiveReconnect.delay(beforeAttempt: 0) == .seconds(1))
        #expect(LiveReconnect.delay(beforeAttempt: 1) == .seconds(2))
        #expect(LiveReconnect.delay(beforeAttempt: 2) == .seconds(5))
        #expect(LiveReconnect.delay(beforeAttempt: 3) == nil)
    }
}

// MARK: - Controller

@MainActor
final class FakePlayback: LivePlaybackControl {
    var isLiveAnswering = false
    var stops = 0
    func stopLivePlayback() { stops += 1 }
}

final class FakeLiveConnection: LiveConnection, @unchecked Sendable {
    let events: AsyncStream<LiveServerEvent>
    private let continuation: AsyncStream<LiveServerEvent>.Continuation
    private let lock = NSLock()
    private var _sent: [Data] = []
    private(set) var closed = false

    init() {
        (events, continuation) = AsyncStream.makeStream(of: LiveServerEvent.self)
    }

    var sent: [JSONValue] { lock.withLock { _sent.compactMap(json) } }

    func send(_ message: Data) async throws { lock.withLock { _sent.append(message) } }
    func close() {
        closed = true
        continuation.finish()
    }

    func emit(_ event: LiveServerEvent) { continuation.yield(event) }
    /// The server closed the socket.
    func drop() { continuation.finish() }
}

final class FakeConnector: LiveConnecting, @unchecked Sendable {
    struct Attempt: Equatable {
        let token: String
        let handle: String?
    }

    private let lock = NSLock()
    private var _attempts: [Attempt] = []
    private var _connections: [FakeLiveConnection] = []
    /// Attempts that fail before succeeding.
    var failuresLeft = 0

    var attempts: [Attempt] { lock.withLock { _attempts } }
    var connections: [FakeLiveConnection] { lock.withLock { _connections } }

    func connect(token: LiveTokenResponse, resumeHandle: String?) async throws -> any LiveConnection {
        try lock.withLock {
            _attempts.append(Attempt(token: token.token, handle: resumeHandle))
            if failuresLeft > 0 {
                failuresLeft -= 1
                throw LiveClientError.closedBeforeSetup(code: 1011, reason: "test")
            }
            let c = FakeLiveConnection()
            _connections.append(c)
            return c
        }
    }
}

@MainActor
final class FakeLiveAudio: LiveAudio {
    var onPlaybackDrained: (@MainActor () -> Void)?
    var queued: [Data] = []
    var flushes = 0
    var micHandler: (@Sendable (Data) -> Void)?
    var isPlayingLiveAudio: Bool { !queued.isEmpty }

    func start() throws {}
    func stop() { queued.removeAll() }
    func enqueuePlayback(_ pcm24k: Data) { queued.append(pcm24k) }
    func flushPlayback() {
        flushes += 1
        queued.removeAll()
    }
    func startMic(onChunk: @escaping @Sendable (Data) -> Void) throws { micHandler = onChunk }
    func stopMic() { micHandler = nil }

    func finishPlaying() {
        queued.removeAll()
        onPlaybackDrained?()
    }
}

@MainActor
final class FakeVoiceHost: VoiceHost {
    var voiceRecipeID: String? = "recipe-1"
    var voiceSessionID: String? = "session-1"
    var voiceStep: VoiceStepContext? = VoiceStepContext(idx: 4, total: 6, title: "Add fillings", instruction: "One even layer, right to the edges.")
    var talking: [(TalkPhase, String)] = []
    var endTalks = 0
    var ran: [CookInput] = []
    var questions: [(caption: String, transcript: String)] = []
    var errors: [String] = []

    func voiceShowTalking(_ phase: TalkPhase, caption: String) { talking.append((phase, caption)) }
    func voiceEndTalking() { endTalks += 1 }
    func voiceRun(_ input: CookInput) {
        ran.append(input)
        if input == .next, let s = voiceStep {
            voiceStep = VoiceStepContext(idx: s.idx + 1, total: s.total, title: "Close", instruction: "Spread side down.")
        }
    }
    func voicePostQuestion(caption: String, transcript: String) { questions.append((caption, transcript)) }
    func voicePostClientError(_ detail: String) { errors.append(detail) }
}

@MainActor
@Suite("Voice controller")
struct VoiceControllerTests {
    let api: MockAPI
    let connector = FakeConnector()
    let audio = FakeLiveAudio()
    let clock = TestClock()
    let host = FakeVoiceHost()
    let tts = TTSFlag()
    let voice: VoiceController

    @MainActor final class TTSFlag { var speaking = false }

    init() throws {
        api = MockAPI(recipe: try FixtureRecipe.load())
        let tts = tts
        voice = VoiceController(
            api: api, connector: connector, audio: audio, clock: clock, ttsIsSpeaking: { tts.speaking },
            requestMicPermission: { true })
        voice.host = host
    }

    private func connected() async throws -> FakeLiveConnection {
        await api.enqueueLiveTokens(liveToken())
        voice.start()
        await eventually("ready") { voice.status == .ready }
        await eventually("mic tap") { audio.micHandler != nil }
        return try #require(connector.connections.last)
    }

    private func contextText(_ message: JSONValue?) -> String? {
        guard case .object(let m)? = message, case .object(let cc)? = m["clientContent"], case .array(let turns)? = cc["turns"],
            case .object(let t)? = turns.first, case .array(let parts)? = t["parts"], case .object(let p)? = parts.first,
            case .string(let text)? = p["text"], cc["turnComplete"] == .bool(false)
        else { return nil }
        return text
    }

    @Test func connectsThenSendsTheStepContextSilently() async throws {
        let conn = try await connected()
        #expect(connector.attempts == [.init(token: "auth_tokens/abc", handle: nil)])
        await eventually("context sent") { !conn.sent.isEmpty }
        #expect(contextText(conn.sent.first) == #"[CONTEXT] Cook is now on step 4 of 6: "Add fillings". Do not reply to this message."#)
    }

    @Test func stepChangeSendsANewContextLine() async throws {
        let conn = try await connected()
        host.voiceStep = VoiceStepContext(idx: 5, total: 6, title: "Close", instruction: "")
        voice.stepDidChange()
        await eventually("second context") { conn.sent.count == 2 }
        #expect(contextText(conn.sent.last)?.contains("step 5 of 6: \"Close\"") == true)
    }

    @Test func failedConnectIsQuietAndRetriesOnTheNextStepWithANewToken() async throws {
        voice.start()  // no token queued: /live-token answers 503
        await eventually("unavailable") { if case .unavailable = voice.status { true } else { false } }
        #expect(host.errors.isEmpty, "a failed first connect is not a client_error")
        await api.enqueueLiveTokens(liveToken(token: "auth_tokens/second"))
        voice.stepDidChange()
        await eventually("ready after retry") { voice.status == .ready }
        #expect(connector.attempts.last?.token == "auth_tokens/second")
        let tokenCalls = await api.calls.filter { if case .liveToken = $0 { true } else { false } }.count
        #expect(tokenCalls == 2)
    }

    @Test func answerShowsCaptionPlaysAndEndsAfterPlaybackWithAQuestionEvent() async throws {
        let conn = try await connected()
        conn.emit(.inputTranscript("why spread it to the edges"))
        await eventually("listening") { host.talking.last?.0 == .listening }
        conn.emit(.audio(Data([1, 2])))
        await eventually("answering") { host.talking.last?.0 == .answering }
        #expect(host.talking.last?.1 == "Answering…")
        conn.emit(.outputTranscript("So every bite has ham and cheese in it."))
        await eventually("caption") { host.talking.last?.1 == "So every bite has ham…" }
        conn.emit(.turnComplete)
        await settle()
        #expect(host.endTalks == 0, "audio is still queued")
        audio.finishPlaying()
        #expect(host.endTalks == 1)
        #expect(host.questions.count == 1)
        #expect(host.questions.first?.transcript == "why spread it to the edges")
        #expect(host.questions.first?.caption == "So every bite has ham…")
    }

    @Test func toolCallRunsTheGestureAndAnswersSilentlyAtOnce() async throws {
        let conn = try await connected()
        await eventually("context") { conn.sent.count == 1 }
        conn.emit(.voiceActivityStart)
        conn.emit(.toolCall([LiveFunctionCall(id: "c1", name: "next_step", args: [:])]))
        await eventually("tool response") { conn.sent.count == 2 }
        #expect(host.ran == [.next])
        let expected = json(#"{"toolResponse":{"functionResponses":[{"id":"c1","name":"next_step","response":{"status":"done","now_on":"5 of 6: Close"},"scheduling":"SILENT"}]}}"#)
        #expect(conn.sent.last == expected)
        // The turnComplete that follows a tool call is not an answer, but it releases the lens.
        conn.emit(.turnComplete)
        await eventually("talking released") { host.endTalks == 1 }
        #expect(host.questions.isEmpty)
    }

    @Test func repeatInstructionIsReadAloudByTheModel() async throws {
        let conn = try await connected()
        await eventually("context") { conn.sent.count == 1 }
        conn.emit(.toolCall([LiveFunctionCall(id: "c2", name: "repeat_instruction", args: [:])]))
        await eventually("tool response") { conn.sent.count == 2 }
        #expect(host.ran.isEmpty)
        #expect(conn.sent.last == json(#"{"toolResponse":{"functionResponses":[{"id":"c2","name":"repeat_instruction","response":{"instruction":"One even layer, right to the edges."}}]}}"#))
    }

    @Test func micGoesOutOnlyWhenTtsIsQuiet() async throws {
        let conn = try await connected()
        await eventually("context") { conn.sent.count == 1 }
        audio.micHandler?(Data(repeating: 7, count: 3200))
        await eventually("chunk sent") { conn.sent.count == 2 }
        tts.speaking = true
        audio.micHandler?(Data(repeating: 8, count: 3200))
        await settle()
        #expect(conn.sent.count == 2, "the model must not hear the app's own TTS")
    }

    @Test func pushToTalkSendsOnlyWhileHeldAndEndsTheStream() async throws {
        voice.micMode = .pushToTalk
        let conn = try await connected()
        await eventually("context") { conn.sent.count == 1 }
        audio.micHandler?(Data(repeating: 1, count: 3200))
        await settle()
        #expect(conn.sent.count == 1)
        voice.pushToTalkHeld = true
        audio.micHandler?(Data(repeating: 2, count: 3200))
        await eventually("held chunk") { conn.sent.count == 2 }
        voice.pushToTalkHeld = false
        await eventually("stream end") { conn.sent.count == 3 }
        #expect(conn.sent.last == json(#"{"realtimeInput":{"audioStreamEnd":true}}"#))
    }

    @Test func liveAudioArrivingWhileTtsSpeaksIsDropped() async throws {
        let conn = try await connected()
        tts.speaking = true
        conn.emit(.audio(Data([1])))
        await settle()
        #expect(audio.queued.isEmpty)
        #expect(!voice.isLiveAnswering)
    }

    @Test func bargeInFlushesPlayback() async throws {
        let conn = try await connected()
        conn.emit(.audio(Data([1])))
        await eventually("queued") { !audio.queued.isEmpty }
        conn.emit(.interrupted)
        await eventually("flushed") { audio.flushes >= 1 }
        #expect(audio.queued.isEmpty)
        #expect(host.talking.last?.0 == .listening)
    }

    @Test func aResultCutsTheAnswerAndLeavesTheTalkingScreen() async throws {
        let conn = try await connected()
        conn.emit(.audio(Data([1])))
        await eventually("answering") { voice.isLiveAnswering }
        voice.stopLivePlayback()
        #expect(audio.queued.isEmpty)
        #expect(host.endTalks == 1)
        #expect(!voice.isLiveAnswering)
        conn.emit(.audio(Data([2])))
        await settle()
        #expect(audio.queued.isEmpty, "the rest of the cut answer is dropped")
    }

    @Test func droppedSocketResumesWithTheSameTokenAndHandle() async throws {
        let conn = try await connected()
        conn.emit(.resumptionUpdate(handle: "h-7", resumable: true))
        await settle()
        conn.drop()
        await eventually("client_error") { host.errors.count == 1 }
        #expect(voice.status == .connecting)
        await eventually("backoff sleep") { clock.pendingCount == 1 }
        clock.advance(by: .seconds(1))
        await eventually("resumed") { connector.connections.count == 2 }
        #expect(connector.attempts.last == .init(token: "auth_tokens/abc", handle: "h-7"))
        await eventually("ready") { voice.status == .ready }
        let resumed = try #require(connector.connections.last)
        await eventually("context resent") { contextText(resumed.sent.first) != nil }
    }

    @Test func goAwayReconnectsAndGivesUpAfterThreeTries() async throws {
        let conn = try await connected()
        // With a handle and a valid token every retry reuses the token (no /live-token calls).
        conn.emit(.resumptionUpdate(handle: "h-1", resumable: true))
        await settle()
        connector.failuresLeft = 3
        conn.emit(.goAway(timeLeft: "5s"))
        for delay in [1, 2, 5] {
            await eventually("sleep \(delay)") { clock.pendingCount == 1 }
            clock.advance(by: .seconds(delay))
        }
        await eventually("gave up") { voice.status == .unavailable("Voice offline") }
        #expect(connector.attempts.count == 4)  // first connect + three retries
    }

    @Test func micPermissionDeniedLeavesVoiceOffButConnected() async throws {
        let denied = VoiceController(
            api: api, connector: connector, audio: audio, clock: clock, ttsIsSpeaking: { false },
            requestMicPermission: { false })
        denied.host = host
        await api.enqueueLiveTokens(liveToken())
        denied.start()
        await eventually("mic denied") { denied.status == .micDenied }
        #expect(audio.micHandler == nil)
    }
}

// MARK: - CookSession as the voice host

@MainActor
@Suite("CookSession voice")
struct CookSessionVoiceTests {
    let recipe: Recipe
    let api: MockAPI
    let clock = TestClock()
    let speech = FakeSpeech()
    let session: CookSession

    init() throws {
        recipe = try FixtureRecipe.load()
        api = MockAPI(recipe: recipe)
        let cacheDir = FileManager.default.temporaryDirectory.appendingPathComponent("CookSessionVoiceTests-\(UUID().uuidString)")
        session = CookSession(
            api: api, frames: FakeFrameSource(), speech: speech, clock: clock, cache: ImageCache(directory: cacheDir),
            watchConfig: { WatcherConfig(enabled: true, threshold: 0.7, interval: .seconds(2.5)) })
    }

    @Test func talkingPausesTheWatcherAndReturnsToTheStep() async throws {
        await session.start(recipe: recipe)
        #expect(session.lens.stepIdx == 1)
        session.voiceShowTalking(.listening, caption: "")
        #expect(session.lens == .talking(phase: .listening, caption: ""))
        #expect(session.isTalking)
        #expect(session.watchGate == .paused)
        session.voiceShowTalking(.answering, caption: "So every bite has filling")
        #expect(session.lens == .talking(phase: .answering, caption: "So every bite has filling"))
        session.voiceEndTalking()
        #expect(session.lens.stepIdx == 1)
        #expect(!session.isTalking)
        if case .open = session.watchGate {} else { Issue.record("watcher should be open again: \(session.watchGate)") }
    }

    @Test func voiceNextPostsAStepChangeViaVoice() async throws {
        await session.start(recipe: recipe)
        session.voiceRun(.next)
        #expect(session.lens.stepIdx == 2)
        await eventually("step_change") { await api.postedEvents.contains { $0.kind == .stepChange } }
        let change = try #require(await api.postedEvents.first { $0.kind == .stepChange })
        #expect(change.payload["via"] == .string("voice"))
        #expect(session.voiceStep == VoiceStepContext(idx: 2, total: recipe.steps.count, title: recipe.steps[1].title, instruction: recipe.steps[1].instruction.isEmpty ? recipe.steps[1].keyLine : recipe.steps[1].instruction))
    }

    @Test func voiceCheckFromTalkingStartsACheckAndTheVerdictReplacesIt() async throws {
        await session.start(recipe: recipe)
        await api.enqueueCheck(.success(checkResponse(.fix, headline: "Filling piled up", fix: "Spread it to the edges")))
        session.voiceShowTalking(.listening, caption: "")
        session.voiceRun(.primary)
        await eventually("fix shown") { session.lens.isFix }
        session.voiceEndTalking()
        #expect(session.lens.isFix, "a verdict is not undone by the end of the turn")
        #expect(!session.isTalking)
    }

    @Test func voiceCheckNeverAdvancesAPass() async throws {
        await session.start(recipe: recipe)
        await api.enqueueCheck(.success(checkResponse(.pass, headline: "Looks right")))
        session.send(.primary)
        await eventually("pass") { session.lens.isPass }
        session.voiceRun(.primary)
        #expect(session.lens.isPass)
    }

    @Test func questionAndLiveErrorsArePosted() async throws {
        await session.start(recipe: recipe)
        session.voicePostQuestion(caption: "So every bite has filling", transcript: "why spread to the edges")
        session.voicePostClientError("socket closed")
        await eventually("two events") { await api.postedEvents.count >= 2 }
        let events = await api.postedEvents
        let question = try #require(events.first { $0.kind == .question })
        #expect(question.payload == ["caption": .string("So every bite has filling"), "transcript": .string("why spread to the edges")])
        let error = try #require(events.first { $0.kind == .clientError })
        #expect(error.payload == ["where": .string("live"), "detail": .string("socket closed")])
    }
}
