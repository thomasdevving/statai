import SwiftUI

/// The cook-along on the phone (IOS-03.3): the lens preview on top, the live camera and the
/// operator's buttons below. The buttons stay permanently: they are the remote on demo day.
struct CookView: View {
    let summary: RecipeSummary

    @Environment(AppEnvironment.self) private var env
    @Environment(\.scenePhase) private var scenePhase
    @State private var session: CookSession?
    @State private var cameraError: String?
    /// Debug builds accept `-openWatcher` to open the watcher sheet, for readout screenshots.
    @State private var showingWatcher = {
        #if DEBUG
            ProcessInfo.processInfo.arguments.contains("-openWatcher")
        #else
            false
        #endif
    }()

    var body: some View {
        Group {
            if let session {
                CookContent(session: session, cameraError: cameraError) {
                    Task { await session.start(recipeID: summary.id) }
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(session?.recipe?.title ?? summary.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Watcher", systemImage: "eye") { showingWatcher = true }
            }
        }
        .sheet(isPresented: $showingWatcher) {
            WatcherSettingsSheet()
        }
        // Settings changes reach the running watcher without restarting the session (IOS-04.4).
        .onChange(of: env.settings.watcherConfig) { _, _ in
            session?.watcherSettingsDidChange()
        }
        // The watcher pauses while the app is in the background (API-CONTRACT §3.3).
        .onChange(of: scenePhase, initial: true) { _, phase in
            session?.setAppActive(phase == .active)
        }
        .task {
            guard session == nil else { return }
            let session = env.makeCookSession()
            self.session = session
            async let camera: Void = startCamera()
            await session.start(recipeID: summary.id)
            await camera
            #if DEBUG
                await Self.autoplayIfRequested(session)
            #endif
        }
        .onChange(of: session?.isActive ?? false, initial: true) { _, active in
            UIApplication.shared.isIdleTimerDisabled = active
        }
        .onDisappear {
            session?.stop()
            env.frameSource.stop()
            UIApplication.shared.isIdleTimerDisabled = false
        }
    }

    #if DEBUG
        /// `-cookAutoplay` presses the operator buttons on a fixed schedule (the same `send` path
        /// the buttons use), so the loop can be screenshotted without touch input.
        /// Timeline (s from step 1): 3 Next, 4 Next, 6 Check, 10 Re-check, (pass, auto-advance),
        /// 16 Next ×3 → Done.
        static func autoplayIfRequested(_ session: CookSession) async {
            guard ProcessInfo.processInfo.arguments.contains("-cookAutoplay") else { return }
            let script: [(Double, CookInput)] = [
                (3, .next), (1, .next), (2, .primary), (4, .primary), (6, .next), (1, .next), (1, .next),
            ]
            for (delay, input) in script {
                try? await Task.sleep(for: .seconds(delay))
                guard !Task.isCancelled else { return }
                print("[autoplay] \(input)")
                session.send(input)
            }
        }
    #endif

    private func startCamera() async {
        do {
            try await env.frameSource.start()
            cameraError = nil
        } catch {
            cameraError = error.localizedDescription
        }
    }
}

private struct CookContent: View {
    let session: CookSession
    let cameraError: String?
    let retry: () -> Void

    @Environment(AppEnvironment.self) private var env
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                switch session.phase {
                case .failed(let message):
                    ContentUnavailableView {
                        Label("Couldn't open this recipe", systemImage: "exclamationmark.triangle")
                    } description: {
                        Text(message)
                    } actions: {
                        Button("Try Again", action: retry).buttonStyle(.borderedProminent)
                    }
                    .padding(.top, 60)
                default:
                    statusRow
                    PhoneLensView(screen: session.lens)
                        .overlay(alignment: .bottom) { preparingOverlay }
                    HStack(alignment: .top, spacing: 12) {
                        cameraTile
                        OperatorControls(session: session)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 16)
        }
        .animation(Motion.standard(reduceMotion: reduceMotion), value: session.phase)
        .sensoryFeedback(trigger: session.lens) { _, new in
            switch new {
            case .pass: .success
            case .fix: .warning
            case .notice: .error
            default: nil
            }
        }
    }

    private var statusRow: some View {
        HStack(spacing: 8) {
            if env.isUsingFixture {
                StatusChip(title: "Bundled fixture", systemImage: "shippingbox", tone: .warning)
            }
            if let check = session.lastCheck {
                StatusChip(title: Self.checkLabel(check), systemImage: "timer", tone: .neutral)
            }
            if let report = session.prefetchReport, !report.failed.isEmpty {
                StatusChip(
                    title: "\(report.failed.count) image\(report.failed.count == 1 ? "" : "s") missing",
                    systemImage: "photo.badge.exclamationmark", tone: .warning)
            }
            Spacer(minLength: 0)
        }
        .frame(minHeight: 28)
    }

    static func checkLabel(_ check: CheckResponse) -> String {
        let ms = check.latencyMs.map { String(format: "%.1f s", Double($0) / 1000) } ?? "—"
        return "Last check \(ms) · \(check.model ?? "?")"
    }

    @ViewBuilder
    private var preparingOverlay: some View {
        if case .preparing(let done, let total) = session.phase {
            // The lens itself says "Preparing N steps…"; this adds only the progress bar.
            Group {
                if total > 0 {
                    ProgressView(value: Double(done), total: Double(total))
                } else {
                    ProgressView()
                }
            }
            .tint(.white)
            .padding(24)
            .frame(maxWidth: .infinity)
            .accessibilityLabel("Preparing steps")
            .transition(.opacity)
        }
    }

    @ViewBuilder
    private var cameraTile: some View {
        ZStack {
            Rectangle().fill(.quaternary)
            if let phone = env.frameSource as? PhoneCameraFrameSource, cameraError == nil {
                CameraPreview(session: phone.captureSession)
            } else if let cameraError {
                VStack(spacing: 6) {
                    Image(systemName: "video.slash").font(.title3)
                    Text(cameraError).font(.caption2).multilineTextAlignment(.center)
                    if let url = URL(string: UIApplication.openSettingsURLString) {
                        Link("Settings", destination: url).font(.caption.weight(.semibold))
                    }
                }
                .padding(8)
                .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 6) {
                    Image(systemName: "photo").font(.title3)
                    Text(env.settings.frameSource.label).font(.caption2).multilineTextAlignment(.center)
                }
                .padding(8)
                .foregroundStyle(.secondary)
            }
        }
        .frame(width: 112, height: 150)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityLabel("Camera preview")
    }
}

/// Buttons mapped to `CookInput`. The primary button's label follows the lens.
private struct OperatorControls: View {
    let session: CookSession

    var body: some View {
        VStack(spacing: 10) {
            if session.isDone {
                Button {
                    session.restart()
                } label: {
                    Label("Restart Session", systemImage: "arrow.counterclockwise")
                        .frame(maxWidth: .infinity, minHeight: 56)
                }
                .buttonStyle(FilledControlStyle(tint: .green))
            } else {
                Button {
                    session.send(.primary)
                } label: {
                    Label(primaryTitle, systemImage: primarySymbol)
                        .frame(maxWidth: .infinity, minHeight: 56)
                }
                .buttonStyle(FilledControlStyle(tint: primaryTint))
                .disabled(!session.isActive || isChecking)
                .accessibilityHint("Same as a pinch on the glasses")
            }

            HStack(spacing: 8) {
                small("Previous", "chevron.left", .previous)
                small("Show Me", "play.rectangle", .showMe)
                small("Next", "chevron.right", .next)
            }
            HStack(spacing: 8) {
                small("Dismiss", "xmark", .dismiss)
                small("Repeat", "speaker.wave.2", .repeatInstruction)
            }
        }
        .disabled(!session.isActive)
    }

    private var isChecking: Bool {
        if case .checking = session.lens { true } else { false }
    }

    private var primaryTitle: String {
        switch session.lens {
        case .checking: "Checking…"
        case .pass: "Next"
        case .fix: "Re-check"
        case .unsure: "Check Again"
        default: "Check"
        }
    }

    private var primarySymbol: String {
        switch session.lens {
        case .pass: "arrow.right"
        case .fix, .unsure: "arrow.clockwise"
        default: "viewfinder"
        }
    }

    private var primaryTint: Color {
        switch session.lens {
        case .pass: .green
        case .fix: .orange
        default: .accentColor
        }
    }

    private func small(_ title: String, _ symbol: String, _ input: CookInput) -> some View {
        Button {
            session.send(input)
        } label: {
            Label(title, systemImage: symbol)
                .labelStyle(StackedLabelStyle())
                .frame(maxWidth: .infinity, minHeight: 44)
        }
        .buttonStyle(TonalControlStyle())
        .disabled(session.isDone && input != .repeatInstruction)
    }
}

private struct StackedLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(spacing: 2) {
            configuration.icon.font(.body.weight(.semibold))
            configuration.title.font(.caption2.weight(.medium)).lineLimit(1).minimumScaleFactor(0.8)
        }
    }
}

/// Primary operator button: solid, with press feedback on touch-down.
private struct FilledControlStyle: ButtonStyle {
    let tint: Color
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .background(
                (isEnabled ? tint : Color.gray).opacity(configuration.isPressed ? 0.8 : 1),
                in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .animation(reduceMotion ? Motion.reduced : Motion.press, value: configuration.isPressed)
    }
}

private struct TonalControlStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(isEnabled ? Color.primary : Color.secondary)
            .background(
                Color(.secondarySystemFill).opacity(configuration.isPressed ? 1 : 0.7),
                in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.96 : 1)
            .animation(reduceMotion ? Motion.reduced : Motion.press, value: configuration.isPressed)
    }
}

#Preview {
    NavigationStack {
        CookView(
            summary: RecipeSummary(
                id: FixtureRecipe.fixtureID(0), title: "Maki roll", chefName: nil, status: .published,
                stepCount: 6, createdAt: nil))
    }
    .environment(AppEnvironment.preview())
}
