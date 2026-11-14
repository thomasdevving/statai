import AudioToolbox
@preconcurrency import AVFoundation
import Foundation
import MWDATInputs

// IOS-08.3 device side: the real capture, the lens while recording, the mark click.

/// Records from the glasses camera when the glasses are ready, the phone camera otherwise, with
/// the microphone, into one MP4.
@MainActor
final class AVTakeCapture: TakeCapturing {
    let source: TakeSource
    private let glasses: GlassesManager
    private let phone: PhoneCameraFrameSource
    private var writer: TakeWriter?
    private var mic: MicCapture?

    init(glasses: GlassesManager, phone: PhoneCameraFrameSource) {
        self.glasses = glasses
        self.phone = phone
        source = glasses.status.isReady ? .glasses : .phone
    }

    func start(writingTo url: URL) async throws {
        try Self.configureAudioSession()
        let writer = TakeWriter(url: url)
        self.writer = writer
        let mic = MicCapture { sample in writer.appendAudio(sample) }
        try await mic.start()
        self.mic = mic
        let deliver: @Sendable (CVPixelBuffer) -> Void = { pixels in
            writer.appendVideo(pixels, at: TakeWriter.hostNow())
        }
        switch source {
        case .glasses:
            guard await glasses.startCookAlong() else {
                mic.stop()
                throw FrameSourceError.configurationFailed("The glasses camera did not start.")
            }
            glasses.frameTap.set(deliver)
        case .phone:
            try await phone.start()
            phone.frameTap.set(deliver)
        }
    }

    func stop() async throws -> TakeCaptureResult {
        glasses.frameTap.set(nil)
        phone.frameTap.set(nil)
        mic?.stop()
        mic = nil
        switch source {
        case .glasses: await glasses.stopCookAlong()
        case .phone: phone.stop()
        }
        guard let writer else { throw TakeWriter.WriterError.noVideo }
        self.writer = nil
        return try await writer.finish()
    }

    /// Record + play; Bluetooth allowed so the glasses' mic can be the input. Which mic is actually
    /// used while the camera streams is IOS-02 proof f (not run yet): check the take's audio.
    private static func configureAudioSession() throws {
        #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .videoRecording, options: [.allowBluetooth, .defaultToSpeaker])
            try session.setActive(true)
        #endif
    }
}

/// "● REC 03:12" / "Step N" on the glasses display; nothing when there is no display.
@MainActor
final class ChefGlassesLens: ChefLens {
    private let glasses: GlassesManager
    private let onMark: @MainActor () -> Void

    init(glasses: GlassesManager, onMark: @escaping @MainActor () -> Void) {
        self.glasses = glasses
        self.onMark = onMark
    }

    func showRecording(elapsed: TimeInterval, step: Int, justMarked: Bool) {
        guard glasses.canDisplay else { return }
        let onMark = onMark
        let card = GlassesCards.recordingCard(elapsed: elapsed, step: step, justMarked: justMarked) {
            Task { @MainActor in onMark() }
        }
        let glasses = glasses
        Task { try? await glasses.showOnLens(card) }
    }

    func clear() {
        let glasses = glasses
        Task { await glasses.clearLens() }
    }
}

/// The short system click on each step mark.
@MainActor
final class ChefClick: ChefFeedback {
    func markClick() {
        AudioServicesPlaySystemSound(1104)
    }
}

/// Wires a recorder to the glasses: a pinch (select) marks a new step while recording.
@MainActor
enum ChefGlassesInputs {
    static func attach(_ recorder: ChefRecorder, to glasses: GlassesManager) {
        glasses.onInput = { [weak recorder] event in
            if case .select = event { recorder?.mark() }
        }
    }

    static func detach(from glasses: GlassesManager) {
        glasses.onInput = nil
    }
}
