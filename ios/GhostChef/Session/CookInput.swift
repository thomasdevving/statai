import Foundation

/// Every way the cook acts. Phone buttons, glasses inputs (IOS-06) and Gemini Live function calls
/// (IOS-05) all produce these values. Named to avoid the DAT SDK's own `InputEvent`.
enum CookInput: Equatable, Sendable {
    /// Check, re-check, or advance now (on a pass).
    case primary
    case next
    case previous
    case showMe
    case dismiss
    case repeatInstruction
}

/// Where an input came from; becomes `via` on `step_change` events (API-CONTRACT §4).
enum InputVia: String, Equatable, Sendable {
    case pinch, swipe, voice, auto, tap
}
