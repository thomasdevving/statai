import Foundation

// Gemini Live wire protocol for the phone (IOS-05.1).
// Every shape here comes from ai/STATUS.md → "Live facts for ios/" (AI-05, run 2026-11-14 over a
// raw WebSocket with an ephemeral token). Live uses camelCase JSON, so nothing here goes through
// `JSONCoding` (that one converts snake_case for our own backend).

enum LiveEndpoint {
    /// The ephemeral-token endpoint. `…Constrained` and the explicit `v1beta` are required for
    /// `auth_tokens/…`; the API-key endpoint `…BidiGenerateContent` is for the backend only.
    static let url = URL(
        string: "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained"
    )!

    /// The token goes in a header (`Authorization: Token auth_tokens/…`). Never log it.
    static func request(token: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 15
        return request
    }

    /// `"models/" + model`, unless the backend already sent the prefix.
    static func modelPath(_ model: String) -> String {
        model.hasPrefix("models/") ? model : "models/\(model)"
    }
}

/// Audio formats on the wire (AI-05 run).
enum LiveAudioFormat {
    /// Mic → server: 16-bit signed LE PCM, mono, 16 kHz.
    static let inputSampleRate: Double = 16_000
    static let inputMimeType = "audio/pcm;rate=16000"
    /// 100 ms of 16 kHz 16-bit mono = 3,200 bytes, sent at real-time pace.
    static let inputChunkBytes = 3_200
    /// Server → speaker: 16-bit LE PCM, mono, 24 kHz.
    static let outputSampleRate: Double = 24_000
}

// MARK: - Outgoing messages

/// One function result for a `toolResponse`.
struct LiveToolResponse: Equatable, Sendable {
    let id: String
    let name: String
    let response: [String: JSONValue]
    /// `true` → `"scheduling": "SILENT"`: add to context, trigger no generation. Used for the four
    /// app-handled commands; `repeat_instruction` omits it so the model reads the text aloud.
    let silent: Bool
}

enum LiveOutgoing {
    /// The first message after the socket opens. When the token is `locked`, only the model and
    /// `sessionResumption` are sent (everything else is bound to the token and a client value is
    /// ignored). `sessionResumption: {}` must be sent to receive resumption handles.
    static func setup(token: LiveTokenResponse, resumeHandle: String?) -> Data {
        var resumption: [String: JSONValue] = [:]
        if let resumeHandle { resumption["handle"] = .string(resumeHandle) }
        var setup: [String: JSONValue] = [
            "model": .string(LiveEndpoint.modelPath(token.model)),
            "sessionResumption": .object(resumption),
        ]
        if !token.locked {
            // Fallback, not expected (AI-05 always mints fully locked). Shape from the SDK.
            let config = token.config
            setup["generationConfig"] = .object([
                "responseModalities": .array(config.responseModalities.map(JSONValue.string))
            ])
            setup["systemInstruction"] = .object([
                "parts": .array([.object(["text": .string(config.systemInstruction)])]),
                "role": .string("user"),
            ])
            setup["tools"] = .array(config.tools.map(renameFunctionDeclarations))
            setup["inputAudioTranscription"] = .object([:])
            setup["outputAudioTranscription"] = .object([:])
            setup["contextWindowCompression"] = .object(["slidingWindow": .object([:])])
        }
        return encode(["setup": .object(setup)])
    }

    /// A typed turn. `turnComplete: false` is how `[CONTEXT]` step lines are sent: the model takes
    /// them in silently (5/5 silent in the AI-05 run; with `true` it sometimes spoke).
    static func text(_ text: String, turnComplete: Bool) -> Data {
        encode([
            "clientContent": .object([
                "turns": .array([
                    .object(["role": .string("user"), "parts": .array([.object(["text": .string(text)])])])
                ]),
                "turnComplete": .bool(turnComplete),
            ])
        ])
    }

    /// One chunk of mic audio (16 kHz 16-bit mono PCM).
    static func audio(_ pcm: Data) -> Data {
        encode([
            "realtimeInput": .object([
                "audio": .object([
                    "data": .string(pcm.base64EncodedString()),
                    "mimeType": .string(LiveAudioFormat.inputMimeType),
                ])
            ])
        ])
    }

    /// Sent when push-to-talk is released (SDK shape; tells the server the mic stopped).
    static func audioStreamEnd() -> Data {
        encode(["realtimeInput": .object(["audioStreamEnd": .bool(true)])])
    }

    static func toolResponse(_ responses: [LiveToolResponse]) -> Data {
        let items: [JSONValue] = responses.map { r in
            var item: [String: JSONValue] = [
                "id": .string(r.id),
                "name": .string(r.name),
                "response": .object(r.response),
            ]
            if r.silent { item["scheduling"] = .string("SILENT") }
            return .object(item)
        }
        return encode(["toolResponse": .object(["functionResponses": .array(items)])])
    }

    /// The backend's `config.tools` keep snake_case (`function_declarations`); the wire wants
    /// `functionDeclarations`. Each declaration (including its `behavior`) is passed through.
    static func renameFunctionDeclarations(_ tool: JSONValue) -> JSONValue {
        guard case .object(var object) = tool else { return tool }
        if let decls = object.removeValue(forKey: "function_declarations") {
            object["functionDeclarations"] = decls
        }
        return .object(object)
    }

    private static func encode(_ value: [String: JSONValue]) -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        // Encoding a JSONValue tree cannot fail.
        return (try? encoder.encode(value)) ?? Data("{}".utf8)
    }
}

// MARK: - Incoming messages

struct LiveFunctionCall: Equatable, Sendable {
    let id: String
    let name: String
    let args: [String: JSONValue]
}

/// What one server frame means. A single frame can carry several (e.g. an audio chunk and a
/// caption piece), so `LiveIncoming.decode` returns a list in wire order.
enum LiveServerEvent: Equatable, Sendable {
    case setupComplete
    /// 24 kHz 16-bit mono PCM.
    case audio(Data)
    /// A piece of the model's caption; concatenate pieces within a turn.
    case outputTranscript(String)
    /// A piece of what the cook said.
    case inputTranscript(String)
    case generationComplete
    case turnComplete
    /// The cook talked over the model: stop playback and drop queued audio (barge-in).
    case interrupted
    case toolCall([LiveFunctionCall])
    case toolCallCancellation([String])
    /// Keep the latest handle where `resumable` is true.
    case resumptionUpdate(handle: String, resumable: Bool)
    case goAway(timeLeft: String?)
    case voiceActivityStart
    case voiceActivityEnd
}

enum LiveIncoming {
    /// Server frames arrive as **binary** WebSocket frames holding UTF-8 JSON (265/265 in the AI-05
    /// run); text frames are accepted too. Unknown or empty messages decode to `[]`.
    static func decode(_ data: Data) -> [LiveServerEvent] {
        guard let root = try? JSONDecoder().decode(JSONValue.self, from: data), case .object(let msg) = root
        else { return [] }
        var events: [LiveServerEvent] = []

        if msg["setupComplete"] != nil { events.append(.setupComplete) }

        if case .object(let content)? = msg["serverContent"] {
            if case .object(let turn)? = content["modelTurn"], case .array(let parts)? = turn["parts"] {
                for case .object(let part) in parts {
                    if case .object(let inline)? = part["inlineData"],
                        case .string(let b64)? = inline["data"],
                        let pcm = Data(base64Encoded: b64)
                    {
                        events.append(.audio(pcm))
                    }
                }
            }
            if case .object(let t)? = content["inputTranscription"], case .string(let text)? = t["text"] {
                events.append(.inputTranscript(text))
            }
            if case .object(let t)? = content["outputTranscription"], case .string(let text)? = t["text"] {
                events.append(.outputTranscript(text))
            }
            if content["interrupted"] == .bool(true) { events.append(.interrupted) }
            if content["generationComplete"] == .bool(true) { events.append(.generationComplete) }
            if content["turnComplete"] == .bool(true) { events.append(.turnComplete) }
        }

        if case .object(let call)? = msg["toolCall"], case .array(let calls)? = call["functionCalls"] {
            let parsed: [LiveFunctionCall] = calls.compactMap { item in
                guard case .object(let c) = item, case .string(let name)? = c["name"] else { return nil }
                let id: String = if case .string(let s)? = c["id"] { s } else { "" }
                let args: [String: JSONValue] = if case .object(let a)? = c["args"] { a } else { [:] }
                return LiveFunctionCall(id: id, name: name, args: args)
            }
            events.append(.toolCall(parsed))
        }

        if case .object(let cancel)? = msg["toolCallCancellation"], case .array(let ids)? = cancel["ids"] {
            events.append(.toolCallCancellation(ids.compactMap { if case .string(let s) = $0 { s } else { nil } }))
        }

        if case .object(let update)? = msg["sessionResumptionUpdate"],
            case .string(let handle)? = update["newHandle"]
        {
            events.append(.resumptionUpdate(handle: handle, resumable: update["resumable"] == .bool(true)))
        }

        if case .object(let away)? = msg["goAway"] {
            let left: String? = if case .string(let s)? = away["timeLeft"] { s } else { nil }
            events.append(.goAway(timeLeft: left))
        }

        if case .object(let activity)? = msg["voiceActivity"], case .string(let type)? = activity["type"] {
            if type == "ACTIVITY_START" { events.append(.voiceActivityStart) }
            if type == "ACTIVITY_END" { events.append(.voiceActivityEnd) }
        }

        return events
    }
}

// MARK: - Captions

enum LiveCaption {
    /// Removes non-speech markers the transcription carries (`<no speech detected>`, `{pause}`) and
    /// collapses whitespace.
    static func clean(_ text: String) -> String {
        var out = ""
        var depth = 0
        for ch in text {
            if ch == "<" || ch == "{" { depth += 1; continue }
            if ch == ">" || ch == "}" { depth = max(0, depth - 1); continue }
            if depth == 0 { out.append(ch) }
        }
        return out.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    /// The lens caption while the model answers: the first `maxWords` words (3–5 per IOS-05.4) of
    /// the output transcription, or "Answering…" before any arrives.
    static func lensCaption(from transcript: String, maxWords: Int = 5) -> String {
        let words = clean(transcript).split(separator: " ")
        guard !words.isEmpty else { return "Answering…" }
        let head = words.prefix(maxWords).joined(separator: " ")
        return words.count > maxWords ? head + "…" : head
    }
}

/// The step-context line from API-CONTRACT §5.1, exactly.
func liveContextLine(stepIdx: Int, total: Int, title: String) -> String {
    "[CONTEXT] Cook is now on step \(stepIdx) of \(total): \"\(title)\". Do not reply to this message."
}
