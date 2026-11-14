import AudioToolbox
import Foundation
import Observation

/// IOS-07 behaviour around one cook-along: backend reachability, audio-only narration, the output
/// mode, and glasses drop-outs (speak, offer the phone camera, resume on the glasses).
@MainActor
@Observable
final class CookResilience {
    /// Set while the glasses are gone during a cook-along that started on them.
    private(set) var glassesDropped: String?
    /// True after "Continue with phone camera" until the glasses return.
    private(set) var usingPhoneFallback = false
    private(set) var switchError: String?
    let reachability: BackendReachability

    @ObservationIgnored private let env: AppEnvironment
    @ObservationIgnored private let session: CookSession
    @ObservationIgnored private var spoken: SpokenLens?
    @ObservationIgnored private let startedOnGlasses: Bool
    @ObservationIgnored weak var link: GlassesCookLink?

    init(env: AppEnvironment, session: CookSession) {
        self.env = env
        self.session = session
        startedOnGlasses = env.isCookingOnGlasses
        reachability = BackendReachability(api: env.api)
    }

    /// Audio-only when forced, when the glasses have no (working) display, or while they are gone;
    /// display-only when speech is muted.
    var outputMode: LensOutputMode {
        LensOutputMode.resolve(
            forcedAudioOnly: env.settings.audioOnlyForced,
            cookingOnGlasses: env.isCookingOnGlasses,
            glassesHaveDisplay: env.glasses.status.supportsDisplay,
            displayFailed: link?.renderer.gaveUp ?? false,
            speechMuted: env.settings.speechMuted)
    }

    func start() {
        if !env.isUsingFixture { reachability.start() }
        let spoken = SpokenLens(
            session: session, speech: env.speech,
            tone: { AudioServicesPlaySystemSound(1057) },  // short tick for "Checking"
            isActive: { [weak self] in self?.outputMode == .audioOnly })
        self.spoken = spoken
        spoken.start()
    }

    func stop() {
        reachability.stop()
        spoken?.stop()
        spoken = nil
    }

    // MARK: Glasses drop-outs (07.4)

    func glassesStatusChanged(from old: GlassesStatus, to new: GlassesStatus) {
        guard startedOnGlasses, session.isActive, let event = GlassesConnectionWatch.event(from: old, to: new) else { return }
        switch event {
        case .disconnected(let reason):
            guard glassesDropped == nil else { return }
            glassesDropped = reason
            // The session keeps its step and timers; checks say "Camera not ready" until the
            // operator switches cameras or the glasses return.
            env.speech.speak("Glasses disconnected.", priority: .result)
        case .reconnected:
            guard glassesDropped != nil else { return }
            glassesDropped = nil
            env.speech.speak("Glasses connected.", priority: .result)
            Task { await resumeOnGlasses() }
        }
    }

    /// "Continue with phone camera".
    func continueWithPhoneCamera() async {
        do {
            try await env.switchCookFrames(to: .phoneCamera)
            usingPhoneFallback = true
            switchError = nil
        } catch {
            switchError = error.localizedDescription
        }
    }

    /// Back to the glasses camera on the same step; the lens card is re-sent by the renderer once
    /// the display restarts.
    private func resumeOnGlasses() async {
        do {
            if usingPhoneFallback {
                try await env.switchCookFrames(to: .glasses)
                usingPhoneFallback = false
            } else {
                try await env.cookFrames?.current.start()
            }
            switchError = nil
        } catch {
            switchError = "Glasses are back but their camera did not start: \(error.localizedDescription)"
        }
    }
}
