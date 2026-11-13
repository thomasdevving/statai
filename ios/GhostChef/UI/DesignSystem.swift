import SwiftUI

// Small shared vocabulary for motion, press feedback, and status chips.
// Principles (Apple "Designing Fluid Interfaces"): feedback on touch-down, critically damped
// springs by default, a cross-fade instead of movement when Reduce Motion is on.

enum Motion {
    /// Default UI spring: no overshoot.
    static let standard = Animation.spring(response: 0.35, dampingFraction: 1)
    /// Press feedback: quick and critically damped.
    static let press = Animation.spring(response: 0.25, dampingFraction: 1)
    /// Reduce Motion replacement: a short fade.
    static let reduced = Animation.easeInOut(duration: 0.2)

    static func standard(reduceMotion: Bool) -> Animation { reduceMotion ? reduced : standard }
}

/// Shrinks on touch-down (not on release) and springs back; fades instead when Reduce Motion is on.
struct PressableButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .opacity(configuration.isPressed && reduceMotion ? 0.7 : 1)
            .animation(reduceMotion ? Motion.reduced : Motion.press, value: configuration.isPressed)
    }
}

extension ButtonStyle where Self == PressableButtonStyle {
    static var pressable: PressableButtonStyle { PressableButtonStyle() }
}

/// A compact capsule that states where data comes from, e.g. "Bundled fixture" or "Fake AI".
struct StatusChip: View {
    enum Tone {
        case neutral, good, warning, bad

        var color: Color {
            switch self {
            case .neutral: .secondary
            case .good: .green
            case .warning: .orange
            case .bad: .red
            }
        }
    }

    let title: String
    let systemImage: String
    var tone: Tone = .neutral

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(tone.color)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(tone.color.opacity(0.14), in: Capsule())
            .accessibilityElement(children: .combine)
    }
}

/// The chef's reference still, or a calm placeholder while it loads or when there is none.
/// Images cross-fade in; nothing slides.
struct ReferenceImage: View {
    let url: URL?
    var cornerRadius: CGFloat = 20

    var body: some View {
        ZStack {
            Rectangle().fill(.quaternary)
            if let url {
                AsyncImage(url: url, transaction: Transaction(animation: Motion.reduced)) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill().transition(.opacity)
                    case .failure:
                        placeholder(symbol: "photo.badge.exclamationmark", text: "Image did not load")
                    default:
                        ProgressView()
                    }
                }
            } else {
                placeholder(symbol: "photo", text: "No reference image yet")
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
        .accessibilityLabel(url == nil ? "No reference image" : "Chef's reference photo")
    }

    private func placeholder(symbol: String, text: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: symbol).font(.title2)
            Text(text).font(.footnote)
        }
        .foregroundStyle(.secondary)
    }
}
