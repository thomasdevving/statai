import Foundation

// IOS-06 rules that do not need the Meta SDK, so they are unit-tested without glasses.
// `GlassesManager`, `DATFrameSource`, `GlassesLensRenderer` and `GlassesInputAdapter` map SDK
// values into these types and apply the answers.

// MARK: - Spike decisions

/// The four IOS-02 decisions IOS-06 builds to (ios/STATUS.md → "Decisions taken from the spike").
/// **None is confirmed on real glasses yet**: these are the spike's working assumptions, kept in
/// one place so a decision taken at the booth is a one-line change.
enum GlassesDecisions {
    /// Lens layout: image + two lines (proof c passed on MockDeviceKit with a 16:10 crop).
    static let lensShowsReferenceImage = true
    /// Frame capture: raw codec, `.high` (720×1280 on the mock), 24 fps; JPEGs scaled per
    /// `FrameSpec`. Mock: ~1–1.6 s to the first frame.
    static let streamFrameRate: UInt = 24
    /// Input mapping: see `GlassesInputMapping.input(for:)`.
    /// Audio route: not decided (proof f not run), so IOS-06.5 is not implemented.
    static let audioRouteDecided = false
}

// MARK: - Connection status (IOS-06.1)

/// What the UI shows about the glasses.
enum GlassesStatus: Equatable, Sendable {
    /// `Wearables.configure()` failed or has not run.
    case unavailable(String)
    /// The app is not registered with the Meta AI app.
    case notRegistered
    case noDevice
    case connecting
    case ready(displays: Bool)
    case disconnected(String)

    var isReady: Bool { if case .ready = self { true } else { false } }

    var supportsDisplay: Bool { if case .ready(let d) = self { d } else { false } }

    var label: String {
        switch self {
        case .unavailable: "Glasses unavailable"
        case .notRegistered: "Glasses not registered"
        case .noDevice: "No glasses"
        case .connecting: "Glasses connecting…"
        case .ready(let displays): displays ? "Glasses ready" : "Glasses ready (no display)"
        case .disconnected(let reason): "Glasses: \(reason)"
        }
    }
}

/// SDK-free snapshot of everything the status depends on. `GlassesManager` fills it from the
/// SDK (`RegistrationState`, the active `Device`'s `DeviceState`, the `DeviceSession` state).
struct GlassesStatusInputs: Equatable, Sendable {
    enum Link: Sendable { case disconnected, connecting, connected }
    enum Session: Sendable { case none, starting, started, paused, stopped }

    var configureError: String?
    var registered = false
    var hasDevice = false
    var link: Link = .disconnected
    var compatible = true
    var hingeClosed = false
    var thermalCritical = false
    var supportsDisplay = false
    var session: Session = .none

    func resolve() -> GlassesStatus {
        if let configureError { return .unavailable(configureError) }
        guard registered else { return .notRegistered }
        guard hasDevice else { return .noDevice }
        guard compatible else { return .disconnected("update required") }
        if hingeClosed { return .disconnected("hinges closed") }
        if thermalCritical { return .disconnected("too hot") }
        switch link {
        case .disconnected: return .disconnected("not connected")
        case .connecting: return .connecting
        case .connected: break
        }
        switch session {
        case .starting: return .connecting
        case .paused: return .disconnected("paused")
        case .none, .stopped, .started: return .ready(displays: supportsDisplay)
        }
    }
}

// MARK: - Frames (IOS-06.2)

enum FrameFreshness {
    /// Frames older than this are not sent: the watcher pauses and a check says "Camera not ready".
    static let maxAge: TimeInterval = 2

    static func isFresh(receivedAt: Date?, now: Date) -> Bool {
        guard let receivedAt else { return false }
        return now.timeIntervalSince(receivedAt) <= maxAge
    }
}

// MARK: - Inputs (IOS-06.4)

/// The device inputs, mirrored from `MWDATInputs.InputEvent` without the SDK.
enum GlassesInputKind: Equatable, Sendable {
    case select
    case back
    case navLeft, navRight, navUp, navDown
    case actionButton
    case capturePress
    case drag
}

enum GlassesInputMapping {
    /// Working mapping (spike assumption; to be confirmed in IOS-02.4):
    /// select (tap / pinch) = Check, right = Next, left = Back, back = Dismiss, up = Show me.
    /// The capture button stays the system's (it takes photos); drags are ignored.
    static func input(for kind: GlassesInputKind) -> CookInput? {
        switch kind {
        case .select: .primary
        case .navRight: .next
        case .navLeft: .previous
        case .back: .dismiss
        case .navUp: .showMe
        case .navDown, .actionButton, .capturePress, .drag: nil
        }
    }

    /// `via` on `step_change` events (API-CONTRACT §4).
    static func via(for kind: GlassesInputKind) -> InputVia {
        switch kind {
        case .navLeft, .navRight, .navUp, .navDown, .drag: .swipe
        default: .pinch
        }
    }
}

/// Ignores the same input repeated within 400 ms (a double-registered pinch must not check twice
/// or skip two steps). Different inputs pass at once.
struct GlassesInputDebouncer {
    static let window: TimeInterval = 0.4

    private var last: (input: CookInput, at: Date)?

    mutating func accept(_ input: CookInput, at now: Date) -> Bool {
        if let last, last.input == input, now.timeIntervalSince(last.at) < Self.window { return false }
        last = (input, now)
        return true
    }
}

// MARK: - Lens layout (IOS-06.3)

/// What one lens screen looks like on the glasses, independent of the display DSL.
/// SDK 1.0.1 text has only `primary` / `secondary` colours (no amber or green), so fix and pass are
/// told apart by icon and words, never by colour.
struct GlassesCardSpec: Equatable, Sendable {
    enum Icon: Equatable, Sendable { case checkmark, warning, info, question, speech, done }

    struct ButtonSpec: Equatable, Sendable {
        let label: String
        let input: CookInput
        let primary: Bool
    }

    var icon: Icon?
    var heading: String
    /// At most two lines besides the heading (display spec).
    var lines: [String]
    var image: ImageRef?
    /// Small grey line, e.g. "● watching" or "Spotted".
    var meta: String?
    var buttons: [ButtonSpec]
}

enum GlassesLensLayout {
    /// `nil` = clear the display.
    static func card(for screen: LensScreen, withButtons: Bool = true) -> GlassesCardSpec? {
        func buttons(_ items: [GlassesCardSpec.ButtonSpec]) -> [GlassesCardSpec.ButtonSpec] {
            withButtons ? items : []
        }
        let check = GlassesCardSpec.ButtonSpec(label: "Check", input: .primary, primary: true)
        let next = GlassesCardSpec.ButtonSpec(label: "Next", input: .next, primary: false)
        let dismiss = GlassesCardSpec.ButtonSpec(label: "Dismiss", input: .dismiss, primary: false)

        switch screen {
        case .step(let card):
            return GlassesCardSpec(
                icon: nil, heading: "\(card.counter)  \(card.title)", lines: [card.keyLine],
                image: GlassesDecisions.lensShowsReferenceImage ? card.refImage : nil,
                meta: watchingText(card.watching), buttons: buttons([check, next]))
        case .checking(let card):
            return GlassesCardSpec(
                icon: nil, heading: "\(card.counter)  \(card.title)", lines: ["Checking…"],
                image: GlassesDecisions.lensShowsReferenceImage ? card.refImage : nil, meta: nil, buttons: [])
        case .fix(let card, let headline, let fix, let proactive):
            return GlassesCardSpec(
                icon: .warning, heading: headline, lines: fix.isEmpty ? [] : [fix],
                image: GlassesDecisions.lensShowsReferenceImage ? card.refImage : nil,
                meta: proactive ? "Spotted" : nil,
                buttons: buttons(proactive ? [check, dismiss] : [GlassesCardSpec.ButtonSpec(label: "Check again", input: .primary, primary: true), dismiss]))
        case .pass(let headline):
            return GlassesCardSpec(
                icon: .checkmark, heading: headline.isEmpty ? "Looks right" : headline, lines: [], image: nil,
                meta: nil, buttons: buttons([next]))
        case .unsure(let headline, let hint):
            return GlassesCardSpec(
                icon: .question, heading: headline, lines: hint.isEmpty ? [] : [hint], image: nil, meta: nil,
                buttons: buttons([check]))
        case .notice(let text):
            return GlassesCardSpec(icon: .info, heading: text, lines: [], image: nil, meta: nil, buttons: [])
        case .talking(let phase, let caption):
            return GlassesCardSpec(
                icon: .speech, heading: phase == .listening ? "Listening…" : "Answering",
                lines: caption.isEmpty ? [] : [caption], image: nil, meta: nil, buttons: [])
        case .showMe(let card):
            return GlassesCardSpec(
                icon: nil, heading: "How the chef did it", lines: [card.keyLine], image: card.refImage,
                meta: "\(card.counter)  \(card.title)", buttons: buttons([dismiss]))
        case .timer(let remaining, let card):
            return GlassesCardSpec(
                icon: nil, heading: "\(card.counter)  \(card.title)", lines: [LensScreen.duration(remaining) + " left"],
                image: nil, meta: nil, buttons: [])
        case .done(let summary):
            let line = summary.map { "\($0.stepsPassedFirstTry) of \($0.stepsTotal) first try · \($0.fixesCaught) fixes caught" }
            return GlassesCardSpec(icon: .done, heading: "Done", lines: line.map { [$0] } ?? [], image: nil, meta: nil, buttons: [])
        case .recipePick(let titles, let selected):
            guard titles.indices.contains(selected) else {
                return GlassesCardSpec(icon: .info, heading: "No recipes yet", lines: [], image: nil, meta: nil, buttons: [])
            }
            return GlassesCardSpec(
                icon: nil, heading: titles[selected], lines: ["Recipe \(selected + 1) of \(titles.count)"], image: nil,
                meta: nil, buttons: [])
        }
    }

    static func watchingText(_ indicator: WatchIndicator) -> String? {
        switch indicator {
        case .active: "● watching"
        case .paused: "○ paused"
        case .offline: "○ offline"
        case .off: nil
        }
    }
}

// MARK: - Display throttle (IOS-06.3)

/// "Send only on change, and no more often than about twice a second."
struct GlassesDisplayThrottle {
    enum Plan: Equatable {
        case skip
        case sendNow
        case sendAfter(TimeInterval)
    }

    static let minInterval: TimeInterval = 0.5

    private(set) var lastSent: GlassesCardSpec??
    private(set) var lastSentAt: Date?

    /// `nil` spec = clear. A clear is never throttled.
    func plan(for spec: GlassesCardSpec?, now: Date) -> Plan {
        if let lastSent, lastSent == spec { return .skip }
        guard spec != nil, let lastSentAt else { return .sendNow }
        let elapsed = now.timeIntervalSince(lastSentAt)
        return elapsed >= Self.minInterval ? .sendNow : .sendAfter(Self.minInterval - elapsed)
    }

    mutating func didSend(_ spec: GlassesCardSpec?, at now: Date) {
        lastSent = .some(spec)
        lastSentAt = now
    }

    mutating func reset() {
        lastSent = nil
        lastSentAt = nil
    }
}
