import SwiftUI

/// Draws any `LensScreen` in a fixed-aspect black panel that imitates the glasses lens
/// (TECH-SPEC "Display spec"): bright elements on black, step counter and title on top, the
/// chef's reference in the middle, at most two short text lines, the watching dot.
/// Amber for fix / warning, green for pass. It only draws; `CookSession` decides.
struct PhoneLensView: View {
    let screen: LensScreen

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Square, like a monocular lens; sized by the width it is given.
    static let aspectRatio: CGFloat = 1

    var body: some View {
        ZStack {
            Color.black
            content
                .id(screen.kind)
                .transition(
                    reduceMotion ? .opacity : .opacity.combined(with: .scale(scale: 0.98)))
        }
        .aspectRatio(Self.aspectRatio, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .environment(\.colorScheme, .dark)
        // The panel has a fixed size; very large text sizes would push lines out of it.
        .dynamicTypeSize(.small ... .xxxLarge)
        .animation(Motion.standard(reduceMotion: reduceMotion), value: screen)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(screen.spokenText ?? "Lens")
        .accessibilityAddTraits(.updatesFrequently)
    }

    @ViewBuilder
    private var content: some View {
        switch screen {
        case .recipePick(let titles, let selected):
            RecipePickLens(titles: titles, selected: selected)
        case .step(let card):
            StepLens(card: card)
        case .checking(let card):
            StepLens(card: card, overlay: .checking)
        case .pass(let headline):
            CenteredLens(symbol: "checkmark.circle.fill", tint: LensColor.pass, headline: headline)
        case .fix(let card, let headline, let fix, let proactive):
            FixLens(card: card, headline: headline, fix: fix, proactive: proactive)
        case .unsure(let headline, let hint):
            CenteredLens(symbol: "questionmark.circle", tint: LensColor.text, headline: headline, line: hint)
        case .talking(let phase, let caption):
            CenteredLens(
                symbol: phase == .listening ? "mic.fill" : "waveform", tint: LensColor.text,
                headline: phase == .listening ? "Listening…" : caption,
                line: phase == .listening ? caption : nil)
        case .showMe(let card):
            StepLens(card: card, overlay: .showMe)
        case .timer(let remaining, let card):
            TimerLens(remainingS: remaining, card: card)
        case .done(let summary):
            DoneLens(summary: summary)
        case .notice(let text):
            CenteredLens(symbol: Self.noticeSymbol(text), tint: LensColor.text, headline: text)
        }
    }

    static func noticeSymbol(_ text: String) -> String {
        switch text {
        case CookSession.Notice.noConnection: "wifi.slash"
        case CookSession.Notice.cameraOff, CookSession.Notice.noFrame: "video.slash"
        case CookSession.Notice.cantCheck: "exclamationmark.icloud"
        case _ where text.hasPrefix("Preparing"): "arrow.down.circle"
        default: "info.circle"
        }
    }
}

enum LensColor {
    static let text = Color.white
    static let dim = Color.white.opacity(0.6)
    static let pass = Color(red: 0.25, green: 0.95, blue: 0.45)
    static let amber = Color(red: 1.0, green: 0.72, blue: 0.1)
    static let offline = Color.white.opacity(0.4)
}

private extension LensScreen {
    /// Identity for cross-fades: a new screen fades, the same screen with new data does not.
    var kind: String {
        switch self {
        case .recipePick: "pick"
        case .step(let c): "step-\(c.idx)"
        case .checking(let c): "checking-\(c.idx)"
        case .pass: "pass"
        case .fix(let c, _, _, _): "fix-\(c.idx)"
        case .unsure: "unsure"
        case .talking: "talking"
        case .showMe(let c): "showMe-\(c.idx)"
        case .timer(_, let c): "timer-\(c.idx)"
        case .done: "done"
        case .notice(let t): "notice-\(t)"
        }
    }
}

// MARK: - Screens

private struct StepLens: View {
    enum Overlay { case none, checking, showMe }

    let card: StepCard
    var overlay: Overlay = .none

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            LensHeader(card: card)
            LensImage(ref: card.refImage)
                .overlay {
                    switch overlay {
                    case .none: EmptyView()
                    case .checking:
                        ZStack {
                            Color.black.opacity(0.55)
                            VStack(spacing: 10) {
                                ProgressView().controlSize(.large).tint(.white)
                                Text("Checking…").font(.title3.weight(.semibold))
                            }
                        }
                    case .showMe:
                        VStack {
                            Spacer()
                            Label("Chef's view", systemImage: "play.rectangle.fill")
                                .font(.footnote.weight(.semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(.black.opacity(0.6), in: Capsule())
                                .padding(8)
                        }
                    }
                }
            Text(card.keyLine)
                .font(.title2.weight(.semibold))
                .lineLimit(2)
                .minimumScaleFactor(0.7)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(LensColor.text)
        .padding(20)
    }
}

private struct FixLens: View {
    let card: StepCard
    let headline: String
    let fix: String
    let proactive: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: proactive ? "eye.trianglebadge.exclamationmark" : "exclamationmark.triangle.fill")
                Text(headline)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Spacer(minLength: 0)
                Text(card.counter)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(LensColor.dim)
            }
            .font(.title.weight(.bold))
            .foregroundStyle(LensColor.amber)
            Rectangle().fill(LensColor.amber.opacity(0.5)).frame(height: 1)
            LensImage(ref: card.refImage)
            Text(fix)
                .font(.title2.weight(.semibold))
                .foregroundStyle(LensColor.amber)
                .lineLimit(2)
                .minimumScaleFactor(0.7)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(20)
    }
}

private struct CenteredLens: View {
    let symbol: String
    let tint: Color
    let headline: String
    var line: String?

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: symbol)
                .font(.system(size: 88, weight: .semibold))
                .foregroundStyle(tint)
            Text(headline)
                .font(.largeTitle.weight(.bold))
                .foregroundStyle(tint == LensColor.pass ? LensColor.pass : LensColor.text)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
            if let line, !line.isEmpty {
                Text(line)
                    .font(.title2.weight(.medium))
                    .foregroundStyle(LensColor.text)
                    .lineLimit(2)
                    .minimumScaleFactor(0.7)
            }
        }
        .multilineTextAlignment(.center)
        .padding(24)
    }
}

private struct DoneLens: View {
    let summary: SessionSummary?

    var body: some View {
        VStack(spacing: 20) {
            Text("Done ✓")
                .font(.system(size: 56, weight: .bold))
                .foregroundStyle(LensColor.pass)
            if let summary {
                HStack(alignment: .top, spacing: 28) {
                    stat("\(summary.stepsPassedFirstTry)/\(summary.stepsTotal)", "right first try")
                    stat("\(summary.fixesCaught)", summary.fixesCaught == 1 ? "fix caught" : "fixes caught")
                }
            }
        }
        .foregroundStyle(LensColor.text)
        .padding(24)
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.system(size: 44, weight: .bold).monospacedDigit())
            Text(label).font(.headline).foregroundStyle(LensColor.dim)
        }
        .accessibilityElement(children: .combine)
    }
}

private struct TimerLens: View {
    let remainingS: Int
    let card: StepCard

    var body: some View {
        VStack(spacing: 12) {
            LensHeader(card: card)
            Spacer(minLength: 0)
            Text(Duration.seconds(max(0, remainingS)), format: .time(pattern: .minuteSecond))
                .font(.system(size: 96, weight: .bold).monospacedDigit())
                .minimumScaleFactor(0.5)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .foregroundStyle(LensColor.text)
        .padding(20)
    }
}

private struct RecipePickLens: View {
    let titles: [String]
    let selected: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Pick a recipe")
                .font(.headline)
                .foregroundStyle(LensColor.dim)
            // Shows the selection and its neighbours; the lens has room for about four rows.
            let lower = max(0, min(selected - 1, titles.count - 4))
            ForEach(Array(titles.enumerated()).filter { $0.offset >= lower && $0.offset < lower + 4 }, id: \.offset) {
                index, title in
                HStack(spacing: 10) {
                    Image(systemName: index == selected ? "chevron.right" : "circle.fill")
                        .font(index == selected ? .title3.weight(.bold) : .system(size: 6))
                        .frame(width: 20)
                    Text(title).lineLimit(1).minimumScaleFactor(0.7)
                }
                .font(.title2.weight(index == selected ? .bold : .regular))
                .foregroundStyle(index == selected ? LensColor.text : LensColor.dim)
                .padding(.vertical, 6)
                .padding(.horizontal, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay {
                    if index == selected {
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(LensColor.text, lineWidth: 2)
                    }
                }
            }
            if titles.isEmpty {
                Text("No recipes yet").font(.title2).foregroundStyle(LensColor.dim)
            }
            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}

// MARK: - Parts

private struct LensHeader: View {
    let card: StepCard

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(card.counter)
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundStyle(LensColor.dim)
                Text(card.title)
                    .font(.title.weight(.bold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
                Spacer(minLength: 0)
                WatchDot(state: card.watching)
            }
            Rectangle().fill(LensColor.text.opacity(0.25)).frame(height: 1)
        }
    }
}

private struct WatchDot: View {
    let state: WatchIndicator

    var body: some View {
        if state != .off {
            HStack(spacing: 5) {
                Circle().fill(color).frame(width: 9, height: 9)
                Text(state == .offline ? "offline" : "watching")
                    .font(.caption.weight(.semibold))
            }
            .foregroundStyle(color)
            .accessibilityElement(children: .combine)
        }
    }

    private var color: Color {
        switch state {
        case .active: LensColor.pass
        case .paused: LensColor.dim
        case .offline, .off: LensColor.offline
        }
    }
}

/// The cached reference still, cropped to 16:10 so both text lines keep their room
/// (the same crop the glasses card uses, IOS-02 proof c).
private struct LensImage: View {
    let ref: ImageRef?

    var body: some View {
        Color.white.opacity(0.08)
            .aspectRatio(16 / 10, contentMode: .fit)
            .overlay {
                if let image = LensImageLoader.image(ref) {
                    Image(uiImage: image).resizable().scaledToFill()
                } else {
                    Image(systemName: "photo")
                        .font(.largeTitle)
                        .foregroundStyle(LensColor.dim)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .frame(maxWidth: .infinity)
            .layoutPriority(-1)
    }
}

// MARK: - Previews (one per LensScreen case)

#if DEBUG
    enum LensPreviewData {
        static var card: StepCard {
            StepCard(
                idx: 3, total: 6, title: "Spread rice", keyLine: "Thin layer, leave 2cm top",
                refImage: Bundle.main.url(forResource: "step-3", withExtension: "jpg", subdirectory: "Fixtures/images")
                    .map { ImageRef(stepID: "preview", fileURL: $0) },
                watching: .active)
        }
        static var allScreens: [(String, LensScreen)] {
            [
                ("recipePick", .recipePick(titles: ["Maki roll", "Onigiri", "Miso soup"], selected: 0)),
                ("step", .step(card)),
                ("checking", .checking(card)),
                ("pass", .pass(headline: "Looks right")),
                ("fix", .fix(card, headline: "Too much rice", fix: "Spread thinner, 2cm nori free", proactive: false)),
                ("fix proactive", .fix(card, headline: "Too much rice", fix: "Spread thinner, 2cm nori free", proactive: true)),
                ("unsure", .unsure(headline: "Can't tell", hint: "Look straight down at mat")),
                ("talking listening", .talking(phase: .listening, caption: "")),
                ("talking answering", .talking(phase: .answering, caption: "Use less rice")),
                ("showMe", .showMe(card)),
                ("timer", .timer(remainingS: 200, card)),
                ("done", .done(SessionSummary(stepsTotal: 6, stepsPassedFirstTry: 5, fixesCaught: 1, warnings: 0, questions: 0))),
                ("done no summary", .done(nil)),
                ("notice", .notice(CookSession.Notice.noConnection)),
            ]
        }
    }

    #Preview("Recipe pick") { PhoneLensView(screen: LensPreviewData.allScreens[0].1).padding() }
    #Preview("Step") { PhoneLensView(screen: .step(LensPreviewData.card)).padding() }
    #Preview("Checking") { PhoneLensView(screen: .checking(LensPreviewData.card)).padding() }
    #Preview("Pass") { PhoneLensView(screen: .pass(headline: "Looks right")).padding() }
    #Preview("Fix") { PhoneLensView(screen: LensPreviewData.allScreens[4].1).padding() }
    #Preview("Fix (watcher)") { PhoneLensView(screen: LensPreviewData.allScreens[5].1).padding() }
    #Preview("Unsure") { PhoneLensView(screen: LensPreviewData.allScreens[6].1).padding() }
    #Preview("Talking – listening") { PhoneLensView(screen: LensPreviewData.allScreens[7].1).padding() }
    #Preview("Talking – answering") { PhoneLensView(screen: LensPreviewData.allScreens[8].1).padding() }
    #Preview("Show me") { PhoneLensView(screen: .showMe(LensPreviewData.card)).padding() }
    #Preview("Timer") { PhoneLensView(screen: LensPreviewData.allScreens[10].1).padding() }
    #Preview("Done") { PhoneLensView(screen: LensPreviewData.allScreens[11].1).padding() }
    #Preview("Notice") { PhoneLensView(screen: .notice(CookSession.Notice.cantCheck)).padding() }
    #Preview("Every screen") {
        ScrollView {
            VStack(spacing: 16) {
                ForEach(LensPreviewData.allScreens, id: \.0) { name, screen in
                    VStack(alignment: .leading) {
                        Text(name).font(.caption)
                        PhoneLensView(screen: screen)
                    }
                }
            }
            .padding()
        }
    }
#endif
