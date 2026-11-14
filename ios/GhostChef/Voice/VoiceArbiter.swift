import Foundation

// Two voices, never at once (IOS-05.6, API-CONTRACT §5.3).
// On-device TTS speaks check verdicts, warnings and notices; Gemini Live speaks only answers.
// These are pure decisions so they can be unit-tested; `ArbitratedSpeech` and `VoiceController`
// apply them.

enum VoiceArbiter {
    enum ResultAction: Equatable {
        /// Live is mid-answer: cut its audio, then speak the result.
        case stopLiveThenSpeak
        case speak
    }

    /// A `.result` (verdict, warning, notice) always wins.
    static func onResult(liveAnswering: Bool) -> ResultAction {
        liveAnswering ? .stopLiveThenSpeak : .speak
    }

    /// Step read-outs (`.info`) are skipped while Live is answering; the lens still updates.
    static func allowsInfo(liveAnswering: Bool) -> Bool {
        !liveAnswering
    }

    /// Mic audio goes to Live only when the cook could be talking to it: never while our own TTS
    /// plays through the speaker (or the model would hear the app and answer it), and in
    /// push-to-talk mode only while the button is held.
    static func shouldSendMic(mode: VoiceMicMode, pushToTalkHeld: Bool, ttsSpeaking: Bool) -> Bool {
        guard !ttsSpeaking else { return false }
        switch mode {
        case .openMic: return true
        case .pushToTalk: return pushToTalkHeld
        }
    }
}

/// IOS-05.3: open mic (the server's voice-activity detection decides turns) or push-to-talk
/// (audio only while a button is held; for a loud stage).
enum VoiceMicMode: String, CaseIterable, Identifiable, Sendable {
    case openMic
    case pushToTalk

    var id: String { rawValue }
    var label: String {
        switch self {
        case .openMic: "Open mic"
        case .pushToTalk: "Push to talk"
        }
    }
}

/// What the app does with Live audio when TTS needs the speaker.
@MainActor
protocol LivePlaybackControl: AnyObject {
    var isLiveAnswering: Bool { get }
    /// Stop Live audio now and drop what is queued.
    func stopLivePlayback()
}

/// Wraps the on-device speech so every `.result` and `.info` goes through the arbiter.
@MainActor
final class ArbitratedSpeech: SpeechOutput {
    private let base: any SpeechOutput
    weak var live: (any LivePlaybackControl)?

    init(base: any SpeechOutput) {
        self.base = base
    }

    var isSpeaking: Bool { base.isSpeaking }

    func speak(_ text: String, priority: SpeechPriority) {
        let answering = live?.isLiveAnswering ?? false
        switch priority {
        case .result:
            if VoiceArbiter.onResult(liveAnswering: answering) == .stopLiveThenSpeak {
                live?.stopLivePlayback()
            }
            base.speak(text, priority: .result)
        case .info:
            guard VoiceArbiter.allowsInfo(liveAnswering: answering) else { return }
            base.speak(text, priority: .info)
        }
    }

    func stop() { base.stop() }
    func playChime() { base.playChime() }
}
