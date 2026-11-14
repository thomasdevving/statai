import SwiftUI

/// Chef mode (IOS-08.3, 08.4): consent → record → name the take → upload → "finish on the review
/// page". Takes whose upload has not finished stay listed (and on the phone) until they do.
struct ChefRecordView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: ChefModel?

    var body: some View {
        Group {
            if let model {
                ChefContent(model: model)
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Chef mode")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            guard model == nil else { return }
            model = ChefModel(env: env)
        }
        .onDisappear {
            model?.leave()
        }
    }
}

/// Owns the recorder, the uploader and the device helpers for the screen's lifetime.
@MainActor
@Observable
final class ChefModel {
    let recorder: ChefRecorder
    let uploader: ChefUploader
    let source: TakeSource
    private(set) var pending: [TakeRecord] = []
    @ObservationIgnored let phoneCamera: PhoneCameraFrameSource
    @ObservationIgnored private let store: TakeStore
    @ObservationIgnored private let glasses: GlassesManager
    @ObservationIgnored private let lens: ChefGlassesLens
    @ObservationIgnored private let click = ChefClick()
    @ObservationIgnored private var backgroundTask: UIBackgroundTaskIdentifier = .invalid

    init(env: AppEnvironment) {
        store = env.takeStore
        glasses = env.glasses
        phoneCamera = env.phoneCamera
        let capture = AVTakeCapture(glasses: env.glasses, phone: env.phoneCamera)
        source = capture.source
        let recorder = ChefRecorder(capture: capture, store: env.takeStore)
        self.recorder = recorder
        lens = ChefGlassesLens(glasses: env.glasses) { [weak recorder] in recorder?.mark() }
        uploader = env.makeChefUploader()
        recorder.attach(lens: lens, feedback: click)
        ChefGlassesInputs.attach(recorder, to: env.glasses)
        refreshPending()
    }

    func refreshPending() {
        pending = store.pending().filter { !$0.title.isEmpty }
    }

    /// Upload with a little extra background time, so a screen lock does not kill a PUT halfway.
    /// (A TUS upload that is cut off resumes from the server's offset on the next try.)
    func upload(_ record: TakeRecord) async {
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "chef-upload") { [weak self] in
            self?.endBackgroundTask()
        }
        await uploader.upload(record)
        endBackgroundTask()
        refreshPending()
    }

    func delete(_ record: TakeRecord) {
        store.delete(record.id)
        refreshPending()
    }

    func leave() {
        ChefGlassesInputs.detach(from: glasses)
        if recorder.isRecording { Task { await recorder.stop() } }
    }

    private func endBackgroundTask() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }
}

private struct ChefContent: View {
    let model: ChefModel
    @State private var title = ""
    @State private var chefName = ""

    private var recorder: ChefRecorder { model.recorder }
    private var uploader: ChefUploader { model.uploader }

    var body: some View {
        Form {
            switch recorder.phase {
            case .idle, .failed:
                if uploader.phase == .idle || isTerminal(uploader.phase) {
                    uploadResult
                    readySection
                } else {
                    uploadSection
                }
            case .recording:
                recordingSection
            case .finishing:
                Section { ProgressView("Saving the recording…") }
            case .naming(let record):
                namingSection(record)
            }
            if !recorder.isRecording, !model.pending.isEmpty {
                pendingSection
            }
        }
    }

    // MARK: Ready

    private var readySection: some View {
        Group {
            Section {
                LabeledContent("Camera", value: model.source.label)
                if model.source == .phone {
                    Label("Glasses not ready: this take is a development fallback and will be labelled as a phone recording.", systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(.orange)
                }
            }
            Section {
                Toggle(isOn: Bindable(recorder).consentGiven) {
                    Text(ChefRecorder.consentText).font(.subheadline)
                }
            } header: {
                Text("Consent")
            } footer: {
                Text("Recording can't start without it. It is sent with the recipe as consent: true.")
            }
            if case .failed(let message) = recorder.phase {
                Section { Text(message).foregroundStyle(.red) }
            }
            Section {
                Button {
                    Task { await recorder.start() }
                } label: {
                    Label("Start Recording", systemImage: "record.circle")
                        .font(.headline).frame(maxWidth: .infinity, minHeight: 50)
                }
                .disabled(!recorder.consentGiven)
            } footer: {
                Text("Talk through each step: the reason, what good looks like, the common mistake. Hold still two seconds on each finished state. Pinch (or tap New Step) at the start of every step.")
            }
        }
    }

    // MARK: Recording

    private var recordingSection: some View {
        Group {
            Section {
                ZStack {
                    if model.source == .phone {
                        CameraPreview(session: model.phoneCamera.captureSession)
                    } else {
                        VStack(spacing: 8) {
                            Image(systemName: "eyeglasses").font(.largeTitle)
                            Text("Recording from the glasses").font(.subheadline)
                        }
                        .foregroundStyle(.secondary)
                    }
                }
                .frame(height: 220)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                HStack {
                    Label(recordingClock(recorder.elapsed), systemImage: "record.circle.fill")
                        .font(.title2.monospacedDigit().bold()).foregroundStyle(.red)
                    Spacer()
                    Text("Step \(recorder.marks.currentStep) · \(recorder.marks.marks.count) mark\(recorder.marks.marks.count == 1 ? "" : "s")")
                        .font(.headline)
                }
            }
            Section {
                Button {
                    recorder.mark()
                } label: {
                    Label("New Step", systemImage: "flag").frame(maxWidth: .infinity, minHeight: 44)
                }
                Button(role: .destructive) {
                    Task { await recorder.stop() }
                } label: {
                    Label("Stop", systemImage: "stop.circle.fill")
                        .font(.title3.bold()).frame(maxWidth: .infinity, minHeight: 60)
                }
            }
        }
    }

    // MARK: Naming

    private func namingSection(_ record: TakeRecord) -> some View {
        Group {
            Section {
                LabeledContent("Length", value: recordingClock(record.durationS))
                LabeledContent("Camera", value: record.source.label)
                LabeledContent("Step marks", value: record.stepMarksS.isEmpty ? "none" : record.stepMarksS.map { recordingClock($0) }.joined(separator: ", "))
            } header: {
                Text("Recorded")
            }
            Section {
                TextField("Title (required)", text: $title)
                TextField("Chef name (optional)", text: $chefName)
                if let error = recorder.titleError {
                    Text(error).font(.footnote).foregroundStyle(.red)
                }
            } header: {
                Text("Recipe")
            } footer: {
                Text("Up to \(ChefRecorder.maxTitleLength) characters. The video stays on the phone until processing has started.")
            }
            Section {
                Button {
                    guard let saved = recorder.finish(title: title, chefName: chefName) else { return }
                    title = ""
                    chefName = ""
                    Task { await model.upload(saved) }
                } label: {
                    Label("Save and Upload", systemImage: "icloud.and.arrow.up").frame(maxWidth: .infinity, minHeight: 44)
                }
                Button("Discard Take", role: .destructive) {
                    recorder.discard()
                    model.refreshPending()
                }
            }
        }
    }

    // MARK: Upload

    private var uploadSection: some View {
        Section {
            switch uploader.phase {
            case .creating:
                ProgressView("Creating the recipe…")
            case .uploading(let method, let sent, let total):
                VStack(alignment: .leading, spacing: 8) {
                    ProgressView(value: Double(sent), total: Double(max(total, 1)))
                    Text("\(method.rawValue): \(sent.formatted(.byteCount(style: .file))) of \(total.formatted(.byteCount(style: .file))) (\(total > 0 ? Int(Double(sent) / Double(total) * 100) : 0)%)")
                        .font(.footnote.monospacedDigit())
                }
            case .retrying(let what, let seconds):
                Label("\(what): retrying in \(seconds) s…", systemImage: "arrow.clockwise")
            case .processing:
                ProgressView("Starting processing…")
            default:
                EmptyView()
            }
        } header: {
            Text("Uploading")
        }
    }

    @ViewBuilder
    private var uploadResult: some View {
        switch uploader.phase {
        case .done(_, let title, let reviewURL):
            Section {
                Label("Processing \"\(title)\"", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                if let reviewURL {
                    Link("Finish on the review page", destination: reviewURL)
                    Text(reviewURL.absoluteString).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                } else {
                    Text("Finish on the review page.")
                }
                if let method = uploader.methodUsed {
                    Text("Uploaded with: \(method.rawValue)").font(.caption).foregroundStyle(.secondary)
                }
            }
        case .failed(let message):
            Section { Text(message).foregroundStyle(.red) }
        default:
            EmptyView()
        }
    }

    private var pendingSection: some View {
        Section {
            ForEach(model.pending) { record in
                VStack(alignment: .leading, spacing: 6) {
                    Text(record.title).font(.headline)
                    Text("\(recordingClock(record.durationS)) · \(record.source == .glasses ? "glasses" : "phone") · \(record.stepMarksS.count) marks")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Upload") { Task { await model.upload(record) } }
                            .buttonStyle(.borderedProminent)
                            .disabled(uploader.isBusy)
                        Button("Delete", role: .destructive) { model.delete(record) }
                            .buttonStyle(.bordered)
                            .disabled(uploader.isBusy)
                    }
                }
            }
        } header: {
            Text("Not uploaded yet")
        }
    }

    private func isTerminal(_ phase: ChefUploader.Phase) -> Bool {
        switch phase {
        case .done, .failed: true
        default: false
        }
    }
}
