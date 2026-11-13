import SwiftUI
import UIKit

/// IOS-02 Glasses Lab: one button per proof, the mock device controls, the mock display
/// preview, the latest camera frame, and a log. Kept for demo-day diagnosis (IOS-02.5).
struct GlassesLabView: View {
    @Environment(GlassesManager.self) private var glasses
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Debug launches put the display preview and frame at the top for screenshots.
    var outputFirst = false

    var body: some View {
        List {
            if outputFirst, glasses.mockDisplayPreview != nil || glasses.lastFrame != nil {
                outputSection
            }
            statusSection
            mockSection
            proofsSection
            if !outputFirst, glasses.mockDisplayPreview != nil || glasses.lastFrame != nil {
                outputSection
            }
            logSection
        }
        .navigationTitle("Glasses Lab")
        .navigationBarTitleDisplayMode(.inline)
        .animation(Motion.standard(reduceMotion: reduceMotion), value: glasses.outcomes)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Stop All", systemImage: "stop.circle") { Task { await glasses.tearDown() } }
            }
        }
    }

    // MARK: Sections

    private var statusSection: some View {
        Section {
            LabeledContent("SDK", value: glasses.configured ? "Configured · 1.0.1" : (glasses.configureError ?? "Not configured"))
            LabeledContent("Registration", value: glasses.registration)
            LabeledContent("Session", value: String(describing: glasses.sessionState))
            LabeledContent("Display", value: glasses.displayState)
            LabeledContent("Frames / inputs", value: "\(glasses.framesReceived) / \(glasses.inputEventsReceived)")
            if glasses.devices.isEmpty {
                Text("No glasses known yet").foregroundStyle(.secondary)
            }
            ForEach(glasses.devices) { device in
                VStack(alignment: .leading, spacing: 2) {
                    Text(device.name).font(.body.weight(.semibold))
                    Text("\(device.type) · link \(device.link) · \(device.compatibility) · display \(device.supportsDisplay ? "yes" : "no")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if !glasses.mockEnabled {
                Button("Register with Meta AI", systemImage: "link") { Task { await glasses.register() } }
            }
        } header: {
            Text("Status")
        }
    }

    private var mockSection: some View {
        Section {
            if glasses.mockPaired {
                Picker(
                    "Camera feed",
                    selection: Binding(
                        get: { glasses.mockFeed },
                        set: { feed in Task { await glasses.setMockFeed(feed) } })
                ) {
                    ForEach(GlassesManager.MockFeed.allCases) { Text($0.label).tag($0) }
                }
                Button("Inject Select / Nav / Back", systemImage: "hand.tap") { glasses.injectMockInputs() }
                Button("Disable MockDeviceKit", systemImage: "xmark.circle", role: .destructive) {
                    Task { await glasses.disableMock() }
                }
            } else {
                Button("Pair Mock Display Glasses", systemImage: "eyeglasses") {
                    Task { await glasses.pairMockDisplayGlasses() }
                }
            }
            Button("Run All Proofs on Mock (≈75 s)", systemImage: "play.square.stack") {
                Task { await glasses.runAllOnMock() }
            }
            .disabled(glasses.outcomes.values.contains { $0.isRunning })
        } header: {
            Text("MockDeviceKit")
        } footer: {
            Text("Simulated Meta Ray-Ban Display glasses. Results here go in the MockDeviceKit column, never the real-glasses one.")
        }
    }

    private var proofsSection: some View {
        Section("Proofs") {
            ForEach(GlassesManager.Proof.allCases) { proof in
                ProofRow(proof: proof, outcome: glasses.outcomes[proof] ?? .notRun) {
                    switch proof {
                    case .a: Task { await glasses.runA() }
                    case .b: Task { await glasses.runB() }
                    case .c: Task { await glasses.runC() }
                    case .d: glasses.runD()
                    case .e: Task { await glasses.runE() }
                    }
                }
            }
            if glasses.outcomes[.b].map({ if case .pass = $0 { true } else { false } }) == true {
                Button("Grab Another Frame", systemImage: "camera") { glasses.grabFrame() }
            }
            if glasses.outcomes[.d]?.isRunning == true {
                Button("Cancel Proof d", systemImage: "xmark", role: .destructive) { glasses.cancelD() }
            }
        }
    }

    private var outputSection: some View {
        Section("Output") {
            if let preview = glasses.mockDisplayPreview {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Mock display").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    MockDisplayPreview(view: preview)
                        .aspectRatio(1, contentMode: .fit)
                        .background(.black)
                        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
                .listRowInsets(EdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16))
            }
            if let frame = glasses.lastFrame {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Latest camera frame").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Image(uiImage: frame)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 280)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    if let info = glasses.lastFrameInfo {
                        Text(info).font(.caption).monospacedDigit().foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var logSection: some View {
        Section("Log") {
            ForEach(glasses.log.reversed().prefix(80)) { line in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(line.at, format: .dateTime.hour().minute().second())
                        .monospacedDigit()
                        .foregroundStyle(.tertiary)
                    Text(line.text)
                }
                .font(.caption)
                .textSelection(.enabled)
            }
        }
    }
}

private struct ProofRow: View {
    let proof: GlassesManager.Proof
    let outcome: GlassesManager.Outcome
    let run: () -> Void

    var body: some View {
        Button(action: run) {
            HStack(alignment: .top, spacing: 12) {
                Text(proof.rawValue)
                    .font(.headline.monospaced())
                    .frame(width: 28, height: 28)
                    .background(tint.opacity(0.15), in: Circle())
                    .foregroundStyle(tint)
                VStack(alignment: .leading, spacing: 3) {
                    Text(proof.title).font(.body.weight(.semibold)).foregroundStyle(.primary)
                    Text(detail).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                statusIcon
            }
            .padding(.vertical, 2)
        }
        .disabled(outcome.isRunning)
        .accessibilityElement(children: .combine)
    }

    private var detail: String {
        switch outcome {
        case .notRun: "PASS when: \(proof.passWhen)"
        case .running(let text), .pass(let text), .fail(let text): text
        }
    }

    private var tint: Color {
        switch outcome {
        case .notRun: .secondary
        case .running: .blue
        case .pass: .green
        case .fail: .red
        }
    }

    @ViewBuilder
    private var statusIcon: some View {
        switch outcome {
        case .notRun: Image(systemName: "play.circle").foregroundStyle(.tint)
        case .running: ProgressView()
        case .pass: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .fail: Image(systemName: "xmark.octagon.fill").foregroundStyle(.red)
        }
    }
}

/// Hosts MockDeviceKit's display preview UIView.
private struct MockDisplayPreview: UIViewRepresentable {
    let view: UIView

    func makeUIView(context: Context) -> UIView {
        let container = UIView()
        container.backgroundColor = .black
        view.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            view.topAnchor.constraint(equalTo: container.topAnchor),
            view.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
        return container
    }

    func updateUIView(_ uiView: UIView, context: Context) {}
}
