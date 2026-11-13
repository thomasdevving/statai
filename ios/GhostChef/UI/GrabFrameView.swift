import SwiftUI
import UIKit

/// Debug tool (IOS-01.5): grabs a JPEG at the /check and /watch sizes and shows whether each is
/// within the contract's limits.
struct GrabFrameView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.openURL) private var openURL

    struct Grab: Identifiable, Equatable {
        let id = UUID()
        let purpose: String
        let maxLongEdge: Int
        let quality: CGFloat
        let maxBytes: Int
        let data: Data
        let pixelSize: CGSize

        var withinLimits: Bool {
            data.count <= maxBytes && Int(max(pixelSize.width, pixelSize.height)) <= maxLongEdge
        }
    }

    enum SourceState: Equatable {
        case starting, running
        case failed(String)
    }

    @State private var sourceState: SourceState = .starting
    @State private var grabs: [Grab] = []
    @State private var grabbing = false
    @State private var lastGrabSucceeded = 0

    var body: some View {
        let source = env.frameSource
        ScrollView {
            VStack(spacing: 20) {
                preview(for: source)
                    .aspectRatio(3 / 4, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .overlay(alignment: .topLeading) { sourceChip.padding(12) }

                if case .failed(let message) = sourceState {
                    failure(message)
                } else {
                    HStack(spacing: 12) {
                        grabButton("Check size", detail: "1280 px · 0.8", spec: FrameSpec.check, source: source)
                        grabButton("Watch size", detail: "512 px · 0.6", spec: FrameSpec.watch, source: source)
                    }
                }

                VStack(spacing: 12) {
                    ForEach(grabs) { GrabResultRow(grab: $0) }
                }
            }
            .padding(20)
            .animation(Motion.standard(reduceMotion: reduceMotion), value: grabs)
        }
        .navigationTitle("Grab a Test Frame")
        .navigationBarTitleDisplayMode(.inline)
        .sensoryFeedback(.success, trigger: lastGrabSucceeded)
        .task(id: env.settings.frameSource) {
            sourceState = .starting
            do {
                try await source.start()
                sourceState = .running
            } catch {
                sourceState = .failed(error.localizedDescription)
            }
        }
        .onDisappear { source.stop() }
    }

    @ViewBuilder
    private func preview(for source: any FrameSource) -> some View {
        if let camera = source as? PhoneCameraFrameSource {
            CameraPreview(session: camera.captureSession)
                .background(.black)
        } else {
            ZStack {
                Rectangle().fill(.quaternary)
                Label("Still test image", systemImage: "photo")
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var sourceChip: some View {
        Group {
            switch sourceState {
            case .starting: Label("Starting", systemImage: "circle.dotted")
            case .running: Label(env.settings.frameSource.label, systemImage: "circle.fill")
            case .failed: Label("Unavailable", systemImage: "exclamationmark.circle")
            }
        }
        .font(.footnote.weight(.semibold))
        .foregroundStyle(sourceState == .running ? .green : .secondary)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial, in: Capsule())
    }

    private func failure(_ message: String) -> some View {
        VStack(spacing: 12) {
            Text(message)
                .font(.callout)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Open iOS Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
            }
            .buttonStyle(.bordered)
        }
    }

    private func grabButton(
        _ title: String, detail: String,
        spec: (maxLongEdge: Int, quality: CGFloat, maxBytes: Int), source: any FrameSource
    ) -> some View {
        Button {
            Task { await grab(title, spec: spec, source: source) }
        } label: {
            VStack(spacing: 2) {
                Text(title).font(.headline)
                Text(detail).font(.caption).monospacedDigit().opacity(0.8)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .foregroundStyle(.white)
            .background(.tint, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.pressable)
        .disabled(grabbing || sourceState != .running)
        .opacity(sourceState == .running ? 1 : 0.5)
    }

    private func grab(
        _ purpose: String, spec: (maxLongEdge: Int, quality: CGFloat, maxBytes: Int),
        source: any FrameSource
    ) async {
        grabbing = true
        defer { grabbing = false }
        guard let data = await source.latestJPEG(maxLongEdge: spec.maxLongEdge, quality: spec.quality),
            let size = JPEGEncoder.pixelSize(of: data)
        else {
            sourceState = .failed("No frame yet. Wait a moment for the camera, then try again.")
            Task {
                try? await Task.sleep(for: .seconds(1.5))
                if case .failed = sourceState { sourceState = .running }
            }
            return
        }
        let grab = Grab(
            purpose: purpose, maxLongEdge: spec.maxLongEdge, quality: spec.quality,
            maxBytes: spec.maxBytes, data: data, pixelSize: size)
        grabs.insert(grab, at: 0)
        if grabs.count > 6 { grabs.removeLast() }
        if grab.withinLimits { lastGrabSucceeded += 1 }
    }
}

private struct GrabResultRow: View {
    let grab: GrabFrameView.Grab

    var body: some View {
        HStack(spacing: 14) {
            if let image = UIImage(data: grab.data) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 54, height: 72)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(grab.purpose).font(.headline)
                Text("\(Int(grab.pixelSize.width)) × \(Int(grab.pixelSize.height)) px")
                    .monospacedDigit()
                Text(
                    "\(grab.data.count.formatted(.byteCount(style: .file))) of \(grab.maxBytes.formatted(.byteCount(style: .file))) max"
                )
                .monospacedDigit()
                .foregroundStyle(.secondary)
            }
            .font(.subheadline)
            Spacer()
            Image(systemName: grab.withinLimits ? "checkmark.circle.fill" : "xmark.octagon.fill")
                .font(.title2)
                .foregroundStyle(grab.withinLimits ? .green : .red)
                .accessibilityLabel(grab.withinLimits ? "Within limits" : "Over the limit")
        }
        .padding(12)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .transition(.opacity)
        .accessibilityElement(children: .combine)
    }
}

#Preview {
    NavigationStack { GrabFrameView() }
        .environment(AppEnvironment.preview())
}
