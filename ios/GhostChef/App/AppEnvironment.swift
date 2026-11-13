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
    @ObservationIgnored private let client: APIClient
    @ObservationIgnored private let mock: MockAPI
    @ObservationIgnored private var frameSources: [FrameSourceKind: any FrameSource] = [:]

    init(settings: Settings = Settings(), session: URLSession = .shared, mock: MockAPI = .fixture()) {
        self.settings = settings
        self.mock = mock
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
        let kind = settings.frameSource
        if let existing = frameSources[kind] { return existing }
        let made: any FrameSource =
            switch kind {
            case .phoneCamera: PhoneCameraFrameSource()
            case .stillImage: StillImageFrameSource.testCard()
            }
        frameSources[kind] = made
        return made
    }

    static func preview(dataSource: Settings.DataSource = .fixture) -> AppEnvironment {
        let defaults = UserDefaults(suiteName: "preview") ?? .standard
        let settings = Settings(defaults: defaults)
        settings.dataSource = dataSource
        return AppEnvironment(settings: settings, mock: .fixture(delay: 0.4))
    }
}
