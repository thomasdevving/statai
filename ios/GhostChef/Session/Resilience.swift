import Foundation

// IOS-07: the rules behind audio-only mode, display-only mode, glasses drop-outs, saved servers
// and the build label. SDK-free and UI-free so they are unit-tested.

// MARK: - Output mode (07.1, 07.2)

/// How the cook-along reaches the wearer.
enum LensOutputMode: String, Equatable, Sendable {
    /// Lens (or phone preview) plus spoken results.
    case normal
    /// No display: every screen is also spoken (07.1). How the app runs on Gen 2 glasses.
    case audioOnly
    /// Speech muted: everything must be readable on the lens (07.2).
    case displayOnly

    var label: String {
        switch self {
        case .normal: "Display + speech"
        case .audioOnly: "Audio only"
        case .displayOnly: "Display only (speech muted)"
        }
    }

    /// Forced audio-only wins; then a missing or failed display while cooking on the glasses;
    /// then muted speech. Muted + no display cannot be honoured silently: audio-only wins, because
    /// a blind and mute session conveys nothing.
    static func resolve(
        forcedAudioOnly: Bool, cookingOnGlasses: Bool, glassesHaveDisplay: Bool, displayFailed: Bool, speechMuted: Bool
    ) -> LensOutputMode {
        if forcedAudioOnly { return .audioOnly }
        if cookingOnGlasses, !glassesHaveDisplay || displayFailed { return .audioOnly }
        if speechMuted { return .displayOnly }
        return .normal
    }
}

/// What audio-only mode adds on a lens change (07.1). `CookSession` already speaks step cards on
/// a step change, every result, notices and Done, so those return nil here (no double speech).
enum AudioOnlyNarration: Equatable, Sendable {
    case speak(String)
    /// "Checking" as a short tone rather than words.
    case checkingTone

    /// `lastStepIdx`: the step number shown before this change (from the last screen with a card).
    static func narration(from previous: LensScreen?, to current: LensScreen, lastStepIdx: Int?) -> AudioOnlyNarration? {
        switch current {
        case .checking:
            if case .checking = previous { return nil }
            return .checkingTone
        case .showMe:
            if case .showMe = previous { return nil }
            return current.spokenText.map(AudioOnlyNarration.speak)
        case .step(let card):
            // Back on the same step after a fix, a "can't tell", a notice or "show me": say where we
            // are again. A new step is already announced by CookSession; a dot change or the end of
            // a question says nothing.
            guard let previous, card.idx == lastStepIdx else { return nil }
            switch previous {
            case .step, .talking, .recipePick, .done: return nil
            default: return .speak("Back to step \(card.idx). \(LensScreen.sentence(card.keyLine))")
            }
        case .timer(let remaining, _):
            if case .timer = previous { return nil }
            return .speak("\(LensScreen.duration(remaining)) left.")
        default:
            return nil
        }
    }
}

// MARK: - Glasses drop-outs (07.4)

enum GlassesConnectionEvent: Equatable, Sendable {
    case disconnected(String)
    case reconnected
}

enum GlassesConnectionWatch {
    /// During a cook-along on the glasses: ready → not ready is a drop-out; not ready → ready is a
    /// return (the caller only acts on it after a drop-out). Connecting alone is neither.
    static func event(from old: GlassesStatus, to new: GlassesStatus) -> GlassesConnectionEvent? {
        switch (old.isReady, new) {
        case (true, .disconnected(let reason)): .disconnected(reason)
        case (true, .noDevice): .disconnected("no glasses")
        case (true, .unavailable(let reason)): .disconnected(reason)
        case (false, .ready): .reconnected
        default: nil
        }
    }
}

// MARK: - Saved servers (07.3)

struct SavedServer: Codable, Equatable, Hashable, Identifiable, Sendable {
    var name: String
    var url: String
    var id: String { name }

    /// Production from backend/STATUS.md; the laptop is the emergency backend on the hotspot.
    static let defaults: [SavedServer] = [
        SavedServer(name: "Production", url: "https://statai-production.up.railway.app"),
        SavedServer(name: "Laptop", url: "http://192.168.1.2:8000"),
    ]

    /// A usable http(s) URL with a host, or nil.
    var validURL: URL? {
        guard let url = URL(string: url.trimmingCharacters(in: .whitespacesAndNewlines)),
            ["http", "https"].contains(url.scheme ?? ""), url.host() != nil
        else { return nil }
        return url
    }
}

// MARK: - Build label (07.6)

enum BuildLabel {
    static let resourceName = "build-label"

    /// "a1b2c3d · 2026-11-14 18:02" written by `ios/scripts/stamp-build.sh`, or "dev build".
    static func current(bundle: Bundle = .main) -> String {
        guard let url = bundle.url(forResource: resourceName, withExtension: "txt"),
            let text = try? String(contentsOf: url, encoding: .utf8)
        else { return "dev build (unstamped)" }
        let line = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return line.isEmpty ? "dev build (unstamped)" : line
    }
}
