import Foundation

// The lens model (ios/README.md "Core design"): one value describes exactly what the lens shows.
// `CookSession` produces it; renderers (phone preview, glasses display, audio-only) only draw it.
// Nothing here knows about SwiftUI or the DAT display DSL.

/// A reference still that is already on disk (IOS-03.5): renderers never touch the network.
struct ImageRef: Equatable, Hashable, Sendable {
    let stepID: String
    /// Local file URL inside the step media cache (or the app bundle for the fixture).
    let fileURL: URL
}

/// The "● watching" dot (IOS-04): green while the watcher sends, grey when paused or offline,
/// hidden when the step has no `watch_fors` or the watcher is switched off.
enum WatchIndicator: String, Equatable, Sendable {
    case active, paused, offline, off
}

/// Gemini Live state (IOS-05).
enum TalkPhase: String, Equatable, Sendable {
    case listening, answering
}

struct StepCard: Equatable, Sendable {
    let idx: Int
    let total: Int
    let title: String
    let keyLine: String
    let refImage: ImageRef?
    let watching: WatchIndicator

    /// "3/8": the step counter as the display spec writes it.
    var counter: String { "\(idx)/\(total)" }

    func with(watching: WatchIndicator) -> StepCard {
        StepCard(idx: idx, total: total, title: title, keyLine: keyLine, refImage: refImage, watching: watching)
    }
}

enum LensScreen: Equatable, Sendable {
    case recipePick(titles: [String], selected: Int)
    case step(StepCard)
    case checking(StepCard)
    case pass(headline: String)
    /// `proactive` = raised by the watcher (IOS-04) rather than by a check.
    case fix(StepCard, headline: String, fix: String, proactive: Bool)
    case unsure(headline: String, hint: String)
    case talking(phase: TalkPhase, caption: String)
    case showMe(StepCard)
    case timer(remainingS: Int, StepCard)
    case done(SessionSummary?)
    /// "No connection", "Can't check right now", "Camera off".
    case notice(String)

    /// The step card behind this screen, when it has one.
    var card: StepCard? {
        switch self {
        case .step(let c), .checking(let c), .showMe(let c), .timer(_, let c): c
        case .fix(let c, _, _, _): c
        default: nil
        }
    }

    /// What the audio-only renderer says for this screen. `nil` = say nothing
    /// (Gemini Live speaks while talking, API-CONTRACT §5.3).
    var spokenText: String? {
        switch self {
        case .recipePick(let titles, let selected):
            guard titles.indices.contains(selected) else { return "No recipes yet." }
            return "Recipe \(selected + 1) of \(titles.count): \(Self.sentence(titles[selected]))"
        case .step(let card):
            return "Step \(card.idx) of \(card.total). \(Self.sentence(card.title)) \(Self.sentence(card.keyLine))"
        case .checking:
            return "Checking."
        case .pass(let headline):
            return Self.sentence(headline)
        case .fix(_, let headline, let fix, _):
            return [headline, fix].filter { !$0.isEmpty }.map(Self.sentence).joined(separator: " ")
        case .unsure(let headline, let hint):
            return [headline, hint].filter { !$0.isEmpty }.map(Self.sentence).joined(separator: " ")
        case .talking:
            return nil
        case .showMe:
            return "Here is how the chef did it."
        case .timer(let remaining, _):
            return "\(Self.duration(remaining)) left."
        case .done(let summary):
            guard let summary else { return "Done. Well cooked." }
            let steps = summary.stepsPassedFirstTry == 1 ? "step" : "steps"
            let fixes = summary.fixesCaught == 1 ? "fix" : "fixes"
            return "Done. \(summary.stepsPassedFirstTry) of \(summary.stepsTotal) \(steps) right first time, "
                + "\(summary.fixesCaught) \(fixes) caught."
        case .notice(let text):
            return Self.sentence(text)
        }
    }

    /// Ends a lens line with a full stop so speech pauses between lines.
    static func sentence(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let last = trimmed.last else { return "" }
        return ".!?".contains(last) ? trimmed : trimmed + "."
    }

    /// 200 → "3 minutes 20 seconds".
    static func duration(_ seconds: Int) -> String {
        let s = max(0, seconds)
        let m = s / 60
        let r = s % 60
        var parts: [String] = []
        if m > 0 { parts.append("\(m) \(m == 1 ? "minute" : "minutes")") }
        if r > 0 || m == 0 { parts.append("\(r) \(r == 1 ? "second" : "seconds")") }
        return parts.joined(separator: " ")
    }
}
