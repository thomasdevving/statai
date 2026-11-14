import Foundation
import Observation

/// User-changeable settings, persisted in UserDefaults. Defaults come from Info.plist, which
/// gets them from Config/Config.xcconfig and the untracked Secrets.xcconfig.
@MainActor
@Observable
final class Settings {
    enum DataSource: String, CaseIterable, Identifiable, Sendable {
        case backend
        case fixture

        var id: String { rawValue }
        var label: String {
            switch self {
            case .backend: "Backend"
            case .fixture: "Bundled fixture"
            }
        }
    }

    enum Key {
        static let baseURL = "settings.baseURL"
        static let demoKey = "settings.demoKey"
        static let dataSource = "settings.dataSource"
        static let frameSource = "settings.frameSource"
        static let watchThreshold = "settings.watchThreshold"
        static let watchEnabled = "settings.watchEnabled"
        static let watchInterval = "settings.watchInterval"
        static let speechMuted = "settings.speechMuted"
        static let voiceEnabled = "settings.voiceEnabled"
        static let voiceMicMode = "settings.voiceMicMode"
    }

    /// API-CONTRACT §3.3 default.
    static let defaultWatchThreshold = 0.7
    /// API-CONTRACT §3.3: seconds from the end of one `/watch` to the next.
    static let defaultWatchInterval = 2.5
    static let watchThresholdRange = 0.5...0.95
    static let watchIntervalRange = 2.0...5.0

    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private let bundle: Bundle

    var baseURLString: String { didSet { defaults.set(baseURLString, forKey: Key.baseURL) } }
    var demoKey: String { didSet { defaults.set(demoKey, forKey: Key.demoKey) } }
    var dataSource: DataSource { didSet { defaults.set(dataSource.rawValue, forKey: Key.dataSource) } }
    var frameSource: FrameSourceKind {
        didSet { defaults.set(frameSource.rawValue, forKey: Key.frameSource) }
    }
    var watchThreshold: Double { didSet { defaults.set(watchThreshold, forKey: Key.watchThreshold) } }
    /// The proactive watcher (IOS-04) on or off.
    var watchEnabled: Bool { didSet { defaults.set(watchEnabled, forKey: Key.watchEnabled) } }
    var watchInterval: Double { didSet { defaults.set(watchInterval, forKey: Key.watchInterval) } }
    /// Silences on-device speech and the pass chime (IOS-03.4).
    var speechMuted: Bool { didSet { defaults.set(speechMuted, forKey: Key.speechMuted) } }
    /// Gemini Live questions and voice commands (IOS-05).
    var voiceEnabled: Bool { didSet { defaults.set(voiceEnabled, forKey: Key.voiceEnabled) } }
    /// Open mic (default) or push-to-talk for a loud stage (IOS-05.3).
    var voiceMicMode: VoiceMicMode { didSet { defaults.set(voiceMicMode.rawValue, forKey: Key.voiceMicMode) } }

    init(defaults: UserDefaults = .standard, bundle: Bundle = .main) {
        self.defaults = defaults
        self.bundle = bundle
        let current = Self.apiConfig(defaults: defaults, bundle: bundle)
        baseURLString = current.baseURL?.absoluteString ?? ""
        demoKey = current.demoKey
        dataSource = defaults.string(forKey: Key.dataSource).flatMap(DataSource.init) ?? .backend
        frameSource =
            defaults.string(forKey: Key.frameSource).flatMap(FrameSourceKind.init)
            ?? FrameSourceKind.selectable.last ?? .phoneCamera
        watchThreshold =
            defaults.object(forKey: Key.watchThreshold) as? Double ?? Self.defaultWatchThreshold
        speechMuted = defaults.bool(forKey: Key.speechMuted)
        watchEnabled = defaults.object(forKey: Key.watchEnabled) as? Bool ?? true
        watchInterval = defaults.object(forKey: Key.watchInterval) as? Double ?? Self.defaultWatchInterval
        voiceEnabled = defaults.object(forKey: Key.voiceEnabled) as? Bool ?? true
        voiceMicMode = defaults.string(forKey: Key.voiceMicMode).flatMap(VoiceMicMode.init) ?? .openMic
    }

    /// What the watcher reads on every tick.
    var watcherConfig: WatcherConfig {
        WatcherConfig(
            enabled: watchEnabled,
            threshold: min(max(watchThreshold, Self.watchThresholdRange.lowerBound), Self.watchThresholdRange.upperBound),
            interval: Duration(
                timeInterval: min(max(watchInterval, Self.watchIntervalRange.lowerBound), Self.watchIntervalRange.upperBound)))
    }

    var apiConfig: APIConfig { Self.apiConfig(defaults: defaults, bundle: bundle) }

    /// Puts the backend URL and key back to the values the app was built with.
    func resetConnectionToBuildDefaults() {
        defaults.removeObject(forKey: Key.baseURL)
        defaults.removeObject(forKey: Key.demoKey)
        let built = Self.apiConfig(defaults: defaults, bundle: bundle)
        baseURLString = built.baseURL?.absoluteString ?? ""
        demoKey = built.demoKey
    }

    /// Reads the connection settings without touching the main actor, so `APIClient` can call it
    /// for every request from any thread.
    nonisolated static func apiConfig(defaults: UserDefaults, bundle: Bundle) -> APIConfig {
        let urlString =
            defaults.string(forKey: Key.baseURL)
            ?? (bundle.object(forInfoDictionaryKey: "APIBaseURL") as? String) ?? ""
        let key =
            defaults.string(forKey: Key.demoKey)
            ?? (bundle.object(forInfoDictionaryKey: "DemoAPIKey") as? String) ?? ""
        let trimmed = urlString.trimmingCharacters(in: .whitespacesAndNewlines)
        return APIConfig(baseURL: trimmed.isEmpty ? nil : URL(string: trimmed), demoKey: key)
    }
}
