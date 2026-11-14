@preconcurrency import AVFoundation
import Foundation

// Live audio in and out (IOS-05.2, IOS-05.3).
// Out: 24 kHz 16-bit mono PCM chunks from Gemini, scheduled on an AVAudioPlayerNode.
// In: the mic through voice processing (echo cancellation), converted to 16 kHz 16-bit mono PCM
// and handed out in 100 ms (3,200-byte) chunks.

/// What `VoiceController` needs from the audio layer. A fake implements it in tests.
@MainActor
protocol LiveAudio: AnyObject {
    /// True while Live audio is queued or playing.
    var isPlayingLiveAudio: Bool { get }
    /// Called when the last queued Live buffer finished playing.
    var onPlaybackDrained: (@MainActor () -> Void)? { get set }
    /// Audio session and engine up (`playAndRecord`, `voiceChat`).
    func start() throws
    /// Engine down; the session goes back to playback-only for TTS.
    func stop()
    func enqueuePlayback(_ pcm24k: Data)
    /// Barge-in or a TTS result: stop now and drop everything queued.
    func flushPlayback()
    /// Starts the mic tap. Chunks arrive on a background thread.
    func startMic(onChunk: @escaping @Sendable (Data) -> Void) throws
    func stopMic()
}

enum MicPermission {
    /// Asks once with the `NSMicrophoneUsageDescription` reason. Denied → voice off, the rest works.
    static func request() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }
}

@MainActor
final class AudioIO: LiveAudio {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    /// Float32 mono at the server's output rate; the mixer resamples to the hardware rate.
    private let playbackFormat = AVAudioFormat(
        commonFormat: .pcmFormatFloat32, sampleRate: LiveAudioFormat.outputSampleRate, channels: 1,
        interleaved: false)!
    private var pendingBuffers = 0
    /// Bumped by `flushPlayback`, so completions of dropped buffers are ignored.
    private var generation = 0
    private var isRunning = false
    private var micHandler: (@Sendable (Data) -> Void)?
    private var observers: [any NSObjectProtocol] = []

    var onPlaybackDrained: (@MainActor () -> Void)?
    var isPlayingLiveAudio: Bool { pendingBuffers > 0 }

    init() {
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: playbackFormat)
    }

    func start() throws {
        guard !isRunning else { return }
        try Self.configureSessionForVoice()
        // Echo cancellation: without it the model hears its own answer and loops (IOS-05.3).
        try engine.inputNode.setVoiceProcessingEnabled(true)
        engine.prepare()
        try engine.start()
        player.play()
        isRunning = true
        observeSessionChanges()
    }

    func stop() {
        stopMic()
        flushPlayback()
        player.stop()
        engine.stop()
        isRunning = false
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
        Self.configureSessionForPlaybackOnly()
    }

    // MARK: Playback

    func enqueuePlayback(_ pcm24k: Data) {
        guard isRunning, let buffer = Self.floatBuffer(fromPCM16: pcm24k, format: playbackFormat) else { return }
        pendingBuffers += 1
        let gen = generation
        player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
            Task { @MainActor in self?.bufferFinished(generation: gen) }
        }
        if !player.isPlaying { player.play() }
    }

    func flushPlayback() {
        generation += 1
        pendingBuffers = 0
        player.stop()  // drops every scheduled buffer
        if isRunning { player.play() }
    }

    private func bufferFinished(generation gen: Int) {
        guard gen == generation, pendingBuffers > 0 else { return }
        pendingBuffers -= 1
        if pendingBuffers == 0 { onPlaybackDrained?() }
    }

    /// 16-bit LE mono PCM → Float32 buffer.
    nonisolated static func floatBuffer(fromPCM16 data: Data, format: AVAudioFormat) -> AVAudioPCMBuffer? {
        let frames = data.count / 2
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)),
            let out = buffer.floatChannelData?[0]
        else { return nil }
        data.withUnsafeBytes { raw in
            for i in 0..<frames {
                let lo = UInt16(raw[2 * i])
                let hi = UInt16(raw[2 * i + 1])
                out[i] = Float(Int16(bitPattern: lo | (hi << 8))) / 32_768
            }
        }
        buffer.frameLength = AVAudioFrameCount(frames)
        return buffer
    }

    // MARK: Mic

    func startMic(onChunk: @escaping @Sendable (Data) -> Void) throws {
        stopMic()
        micHandler = onChunk
        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard let resampler = MicResampler(inputFormat: inputFormat, onChunk: onChunk) else {
            throw AudioIOError.unsupportedInputFormat
        }
        // ~100 ms per tap callback at the hardware rate.
        let bufferSize = AVAudioFrameCount(max(256, inputFormat.sampleRate / 10))
        input.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { buffer, _ in
            resampler.process(buffer)
        }
    }

    func stopMic() {
        guard micHandler != nil else { return }
        engine.inputNode.removeTap(onBus: 0)
        micHandler = nil
    }

    // MARK: Session

    private static func configureSessionForVoice() throws {
        #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            // defaultToSpeaker only redirects from the earpiece; a headset or the glasses still win.
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.allowBluetooth, .defaultToSpeaker])
            try session.setActive(true)
        #endif
    }

    private static func configureSessionForPlaybackOnly() {
        #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            try? session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
            try? session.setActive(true)
        #endif
    }

    /// A phone call, a disconnected headset or the glasses: rebuild the engine, keep the socket.
    private func observeSessionChanges() {
        guard observers.isEmpty else { return }
        let center = NotificationCenter.default
        let rebuild: @Sendable (Notification) -> Void = { [weak self] _ in
            Task { @MainActor in self?.rebuildEngine() }
        }
        observers.append(center.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil, using: rebuild))
        #if os(iOS)
            observers.append(center.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: nil, using: rebuild))
            observers.append(
                center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: nil) { [weak self] note in
                    let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
                    guard raw == AVAudioSession.InterruptionType.ended.rawValue else { return }
                    Task { @MainActor in self?.rebuildEngine() }
                })
        #endif
    }

    private func rebuildEngine() {
        guard isRunning else { return }
        let handler = micHandler
        stopMic()
        flushPlayback()
        engine.stop()
        isRunning = false
        do {
            try start()
            if let handler { try startMic(onChunk: handler) }
        } catch {
            print("[voice] audio rebuild failed: \(error.localizedDescription)")
        }
    }
}

enum AudioIOError: Error, LocalizedError {
    case unsupportedInputFormat

    var errorDescription: String? { "The microphone format can't be converted for Live" }
}

/// Runs on the audio thread: converts tap buffers to 16 kHz Int16 mono and emits 3,200-byte chunks.
final class MicResampler: @unchecked Sendable {
    private let converter: AVAudioConverter
    private let outputFormat: AVAudioFormat
    private let onChunk: @Sendable (Data) -> Void
    private let lock = NSLock()
    private var pending = Data()

    init?(inputFormat: AVAudioFormat, onChunk: @escaping @Sendable (Data) -> Void) {
        guard
            let out = AVAudioFormat(
                commonFormat: .pcmFormatInt16, sampleRate: LiveAudioFormat.inputSampleRate, channels: 1,
                interleaved: true),
            let converter = AVAudioConverter(from: inputFormat, to: out)
        else { return nil }
        self.converter = converter
        outputFormat = out
        self.onChunk = onChunk
    }

    func process(_ buffer: AVAudioPCMBuffer) {
        let ratio = outputFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else { return }
        var supplied = false
        var error: NSError?
        let status = converter.convert(to: out, error: &error) { _, inputStatus in
            if supplied {
                inputStatus.pointee = .noDataNow
                return nil
            }
            supplied = true
            inputStatus.pointee = .haveData
            return buffer
        }
        guard status != .error, out.frameLength > 0, let samples = out.int16ChannelData?[0] else { return }
        let bytes = Data(bytes: samples, count: Int(out.frameLength) * 2)
        let chunks: [Data] = lock.withLock {
            pending.append(bytes)
            var ready: [Data] = []
            while pending.count >= LiveAudioFormat.inputChunkBytes {
                ready.append(pending.prefix(LiveAudioFormat.inputChunkBytes))
                pending.removeFirst(LiveAudioFormat.inputChunkBytes)
            }
            return ready
        }
        chunks.forEach(onChunk)
    }
}
