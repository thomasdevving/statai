import SwiftUI

/// Connection, server health, camera, and watcher settings. Changes apply immediately.
struct SettingsView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        @Bindable var settings = env.settings

        NavigationStack {
            Form {
                Section {
                    Picker("Data", selection: $settings.dataSource) {
                        ForEach(Settings.DataSource.allCases) { Text($0.label).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())

                    if settings.dataSource == .backend {
                        // Stacked label + bordered field, so these read as inputs, not values.
                        InputRow(title: "Backend URL", systemImage: "network") {
                            TextField("http://192.168.1.20:8000", text: $settings.baseURLString)
                                .keyboardType(.URL)
                                .textContentType(.URL)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .submitLabel(.done)
                        }
                        InputRow(title: "Demo key", systemImage: "key") {
                            SecureField("Ask the backend owner", text: $settings.demoKey)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .submitLabel(.done)
                        }
                        Button("Reset to Build Defaults") { settings.resetConnectionToBuildDefaults() }
                    }
                } header: {
                    Text("Server")
                } footer: {
                    Text(
                        settings.dataSource == .backend
                            ? "Use a teammate's laptop on this Wi-Fi or the deployed URL from backend/STATUS.md."
                            : "Recipes come from the fixture bundled in the app. Use this only for UI work; demos must use the backend."
                    )
                }

                HealthSection()

                Section {
                    Picker("Frame source", selection: $settings.frameSource) {
                        ForEach(FrameSourceKind.selectable) { Text($0.label).tag($0) }
                    }
                    NavigationLink {
                        GrabFrameView()
                    } label: {
                        Label("Grab a Test Frame", systemImage: "camera.viewfinder")
                    }
                } header: {
                    Text("Camera")
                } footer: {
                    Text("Glasses become a frame source once the glasses integration lands.")
                }

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        LabeledContent("Alert confidence") {
                            Text(settings.watchThreshold, format: .number.precision(.fractionLength(2)))
                                .monospacedDigit()
                        }
                        Slider(value: $settings.watchThreshold, in: 0.5...0.95, step: 0.05) {
                            Text("Alert confidence")
                        } minimumValueLabel: {
                            Text("0.5")
                        } maximumValueLabel: {
                            Text("0.95")
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                    if settings.watchThreshold != Settings.defaultWatchThreshold {
                        Button("Reset to 0.70") { settings.watchThreshold = Settings.defaultWatchThreshold }
                    }
                } header: {
                    Text("Watcher")
                } footer: {
                    Text("A mistake is shown only after two checks in a row agree at this confidence or higher.")
                }

                Section("About") {
                    LabeledContent("App version", value: Bundle.main.versionString)
                    LabeledContent("API contract", value: "\(Health.supportedContractMajor).x")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

/// `GET /health`, with a clear warning when the server is on fake AI or an incompatible contract.
private struct HealthSection: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    enum State: Equatable {
        case idle, checking
        case ok(Health)
        case failed(String)
    }

    @SwiftUI.State private var state: State = .idle

    /// Re-check when the connection changes; the short delay avoids a request per keystroke.
    private var connectionKey: String {
        "\(env.settings.dataSource.rawValue)|\(env.settings.baseURLString)|\(env.settings.demoKey)"
    }

    var body: some View {
        Section {
            switch state {
            case .idle, .checking:
                HStack(spacing: 10) {
                    ProgressView()
                    Text("Checking server…").foregroundStyle(.secondary)
                }
            case .failed(let message):
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Server unreachable").font(.body.weight(.semibold))
                        Text(message).font(.footnote).foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "bolt.horizontal.circle.fill").foregroundStyle(.red)
                }
            case .ok(let health):
                if health.isFakeAI {
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("AI mode: \(health.aiMode)").font(.body.weight(.semibold))
                            Text("Verdicts are not from Gemini. Do not demo in this mode.")
                                .font(.footnote)
                        }
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill")
                    }
                    .foregroundStyle(.orange)
                    .listRowBackground(Color.orange.opacity(0.12))
                } else {
                    Label("AI mode: Gemini", systemImage: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                }
                LabeledContent("Status", value: health.status)
                LabeledContent("Storage", value: health.storage)
                LabeledContent("Contract") {
                    HStack(spacing: 6) {
                        Text(health.contractVersion)
                        if !health.isCompatibleContract {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(.red)
                                .accessibilityLabel("Incompatible")
                        }
                    }
                }
            }

            Button {
                Task { await check() }
            } label: {
                Label("Check Again", systemImage: "arrow.clockwise")
            }
            .disabled(state == .checking)
        } header: {
            Text("Server health")
        }
        .animation(Motion.standard(reduceMotion: reduceMotion), value: state)
        .task(id: connectionKey) {
            try? await Task.sleep(for: .milliseconds(400))
            guard !Task.isCancelled else { return }
            await check()
        }
    }

    private func check() async {
        state = .checking
        do {
            state = .ok(try await env.api.health())
        } catch is CancellationError {
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

/// A caption label above a tinted, bordered input, with a pencil to signal it can be edited.
private struct InputRow<Field: View>: View {
    let title: String
    let systemImage: String
    @ViewBuilder var field: Field
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                field
                    .font(.body.monospaced())
                    .focused($focused)
                Image(systemName: "pencil")
                    .foregroundStyle(.tint)
                    .opacity(focused ? 0 : 1)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color(.tertiarySystemFill), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(focused ? Color.accentColor : .clear, lineWidth: 1.5)
            )
            .contentShape(Rectangle())
            .onTapGesture { focused = true }
        }
        .padding(.vertical, 4)
    }
}

extension Bundle {
    var versionString: String {
        let short = object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        let build = object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"
        return "\(short) (\(build))"
    }
}

#Preview {
    SettingsView().environment(AppEnvironment.preview())
}
