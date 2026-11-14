@preconcurrency import AVFoundation
import Foundation

enum SpeechPriority: Sendable {
    /// A check result or notice: interrupts anything being said and drops queued info.
    case result
    /// Step announcements and similar: queued behind what is playing; dropped if a result arrives.
    case info
}

/// On-device speech for results (API-CONTRACT §5.3: `spoken` strings are always spoken locally).
@MainActor
protocol SpeechOutput: AnyObject {
    func speak(_ text: String, priority: SpeechPriority)
    func stop()
    var isSpeaking: Bool { get }
    /// The short pass chime (display spec screen 4).
    func playChime()
}

/// `AVSpeechSynthesizer` with an English voice, slightly faster than default, plus a generated chime.
@MainActor
final class SystemSpeechOutput: NSObject, SpeechOutput {
    private let synthesizer = AVSpeechSynthesizer()
    private let isMuted: @MainActor () -> Bool
    private var audioSessionConfigured = false
    private var chimePlayer: AVAudioPlayer?
    private var lastChimeAt: Date?
    private lazy var voice: AVSpeechSynthesisVoice? = Self.bestEnglishVoice()

    /// Default rate × 1.1: results are short and the cook is busy.
    static let rate = min(AVSpeechUtteranceMaximumSpeechRate, AVSpeechUtteranceDefaultSpeechRate * 1.1)

    init(isMuted: @escaping @MainActor () -> Bool = { false }) {
        self.isMuted = isMuted
        super.init()
    }

    var isSpeaking: Bool { synthesizer.isSpeaking }

    func speak(_ text: String, priority: SpeechPriority) {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isMuted() else { return }
        configureAudioSessionIfNeeded()
        if priority == .result, synthesizer.isSpeaking {
            // Cuts the current sentence and everything queued behind it.
            synthesizer.stopSpeaking(at: .immediate)
        }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = voice
        utterance.rate = Self.rate
        // Let a chime that just started ring before the voice comes in.
        if let lastChimeAt, Date.now.timeIntervalSince(lastChimeAt) < 0.3 {
            utterance.preUtteranceDelay = 0.3
        }
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }

    func playChime() {
        guard !isMuted() else { return }
        configureAudioSessionIfNeeded()
        if chimePlayer == nil {
            chimePlayer = try? AVAudioPlayer(data: Chime.wav, fileTypeHint: AVFileType.wav.rawValue)
            chimePlayer?.prepareToPlay()
        }
        chimePlayer?.currentTime = 0
        chimePlayer?.play()
        lastChimeAt = .now
    }

    /// `.playback` so results are heard with the ring switch on silent. IOS-05 switches to
    /// `.playAndRecord` for Gemini Live; that session also plays TTS, so it is left alone (switching
    /// it back would cut the mic).
    private func configureAudioSessionIfNeeded() {
        guard !audioSessionConfigured else { return }
        audioSessionConfigured = true
        let session = AVAudioSession.sharedInstance()
        guard session.category != .playAndRecord else { return }
        do {
            try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try session.setActive(true)
        } catch {
            print("[speech] audio session setup failed: \(error.localizedDescription)")
        }
    }

    /// Prefers premium / enhanced en-US voices when installed, else the default en-US voice.
    private static func bestEnglishVoice() -> AVSpeechSynthesisVoice? {
        let english = AVSpeechSynthesisVoice.speechVoices().filter { $0.language == "en-US" }
        return english.first { $0.quality == .premium }
            ?? english.first { $0.quality == .enhanced }
            ?? AVSpeechSynthesisVoice(language: "en-US")
    }
}

/// A short two-note chime rendered in code (no bundled audio asset to license).
enum Chime {
    static let wav: Data = render()

    private static func render() -> Data {
        let sampleRate = 44_100
        let notes: [(freq: Double, start: Double, length: Double)] = [
            (1318.5, 0.0, 0.22),  // E6
            (1760.0, 0.09, 0.30),  // A6
        ]
        let total = Int(Double(sampleRate) * 0.42)
        var samples = [Int16](repeating: 0, count: total)
        for i in 0..<total {
            let t = Double(i) / Double(sampleRate)
            var v = 0.0
            for note in notes where t >= note.start && t < note.start + note.length {
                let local = t - note.start
                let attack = min(1, local / 0.005)
                let decay = exp(-local * 14)
                v += sin(2 * .pi * note.freq * local) * attack * decay * 0.35
            }
            samples[i] = Int16(max(-1, min(1, v)) * Double(Int16.max))
        }
        var data = Data()
        func append<T: FixedWidthInteger>(_ value: T) {
            withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
        }
        let byteCount = samples.count * 2
        data.append(contentsOf: Array("RIFF".utf8))
        append(UInt32(36 + byteCount))
        data.append(contentsOf: Array("WAVEfmt ".utf8))
        append(UInt32(16))
        append(UInt16(1))  // PCM
        append(UInt16(1))  // mono
        append(UInt32(sampleRate))
        append(UInt32(sampleRate * 2))
        append(UInt16(2))
        append(UInt16(16))
        data.append(contentsOf: Array("data".utf8))
        append(UInt32(byteCount))
        for s in samples { append(s) }
        return data
    }
}
