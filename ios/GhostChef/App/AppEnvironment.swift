import Foundation
import Observation

/// The app's dependency container: settings, the API, and the active frame source.
/// Injected through the SwiftUI environment.
@MainActor
@Observable
final class AppEnvironment {
    let settings: Settings
    /// Meta Wearables SDK: registration, devices, session, Glasses Lab proofs (IOS-02).
    let glasses = GlassesManager()
    /// On-device speech + chime for results (IOS-03.4); follows the mute toggle in Settings.
    let speech: SystemSpeechOutput
    /// Step media on disk (IOS-03.5).
    let imageCache = ImageCache()
    /// The last ten watcher results, shown in Settings for tuning (IOS-04.4).
    let watchLog = WatchLog()
    @ObservationIgnored private let client: APIClient
    @ObservationIgnored private let mock: MockAPI
    @ObservationIgnored private var frameSources: [FrameSourceKind: any FrameSource] = [:]

    init(settings: Settings = Settings(), session: URLSession = .shared, mock: MockAPI = .fixture(delay: 0.8, mimicFakeAI: true)) {
        self.settings = settings
        self.mock = mock
        self.speech = SystemSpeechOutput(isMuted: { [settings] in settings.speechMuted })
        self.client = APIClient(session: session) {
            Settings.apiConfig(defaults: .standard, bundle: .main)
        }
    }

    /// The API for the selected data source. Read it at the point of use; it follows Settings.
    var api: any GhostChefAPI {
        settings.dataSource == .fixture ? mock : client
    }

    var isUsingFixture: Bool { settings.dataSource == .fixture }

    /// The frame source chosen in Settings. Instances are created once and reused.
    var frameSource: any FrameSource {
        source(for: settings.frameSource)
    }

    /// The frame source a cook-along uses, fixed when the session is made: the glasses camera
    /// whenever the glasses are ready at that moment (IOS-06.2), otherwise the Settings choice.
    private(set) var cookFrameSourceKind: FrameSourceKind?

    var cookFrameSource: any FrameSource {
        source(for: cookFrameSourceKind ?? settings.frameSource)
    }

    var isCookingOnGlasses: Bool { (cookFrameSourceKind ?? settings.frameSource) == .glasses }

    private func source(for kind: FrameSourceKind) -> any FrameSource {
        if let existing = frameSources[kind] { return existing }
        let made: any FrameSource =
            switch kind {
            case .phoneCamera: PhoneCameraFrameSource()
            case .stillImage: StillImageFrameSource.testCard()
            case .glasses: DATFrameSource(glasses: glasses)
            }
        frameSources[kind] = made
        return made
    }

    /// A new cook-along wired to the current data source, frame source, and speech output.
    func makeCookSession() -> CookSession {
        let settings = settings
        let kind: FrameSourceKind = glasses.status.isReady ? .glasses : settings.frameSource
        cookFrameSourceKind = kind
        let frameSource = source(for: kind)
        // Every result and step read-out goes through the arbiter so TTS and Live never overlap
        // (IOS-05.6).
        let arbitrated = ArbitratedSpeech(base: speech)
        let session = CookSession(
            api: api, frames: frameSource, speech: arbitrated, cache: imageCache,
            deviceLabel: kind == .glasses ? "Glasses + iPhone" : "iPhone (\(kind.label))",
            watchConfig: { settings.watcherConfig }, watchLog: watchLog)
        if settings.voiceEnabled {
            let speech = speech
            let voice = VoiceController(
                api: api, audio: AudioIO(), ttsIsSpeaking: { speech.isSpeaking })
            voice.micMode = settings.voiceMicMode
            arbitrated.live = voice
            session.voice = voice
        }
        return session
    }

    // MARK: Chef mode (IOS-08)

    /// The phone camera instance (shared with the cook-along; one capture session).
    var phoneCamera: PhoneCameraFrameSource {
        if let existing = source(for: .phoneCamera) as? PhoneCameraFrameSource { return existing }
        let made = PhoneCameraFrameSource()
        frameSources[.phoneCamera] = made
        return made
    }

    let takeStore = TakeStore()

    /// The review page for a processed take: `<API base>/app/review/` (WEB-02).
    var reviewPageURL: URL? {
        settings.apiConfig.baseURL?.appending(path: "app/review/")
    }

    func makeChefUploader() -> ChefUploader {
        ChefUploader(
            api: api, transport: URLSessionUploadTransport(), store: takeStore,
            reviewURL: { [weak self] in self?.reviewPageURL })
    }

    /// A voice controller for Settings → Voice Lab (no cook-along around it).
    func makeVoiceLabController() -> VoiceController {
        let speech = speech
        let voice = VoiceController(api: api, audio: AudioIO(), ttsIsSpeaking: { speech.isSpeaking })
        voice.micMode = settings.voiceMicMode
        return voice
    }

    static func preview(dataSource: Settings.DataSource = .fixture) -> AppEnvironment {
        let defaults = UserDefaults(suiteName: "preview") ?? .standard
        let settings = Settings(defaults: defaults)
        settings.dataSource = dataSource
        return AppEnvironment(settings: settings, mock: .fixture(delay: 0.4, mimicFakeAI: true))
    }
}
