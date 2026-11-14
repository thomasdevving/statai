import SwiftUI

/// Watcher on/off, alert confidence, interval, and the last ten `/watch` results (IOS-04.4).
/// Used in Settings and in the cook screen's watcher sheet; every change applies on the next tick.
struct WatcherSettingsSection: View {
    @Environment(AppEnvironment.self) private var env

    var body: some View {
        @Bindable var settings = env.settings

        Section {
            Toggle(isOn: $settings.watchEnabled) {
                Label("Watch While Cooking", systemImage: "eye")
            }
            if settings.watchEnabled {
                SliderRow(
                    title: "Alert confidence", value: $settings.watchThreshold,
                    range: Settings.watchThresholdRange, step: 0.05,
                    format: .number.precision(.fractionLength(2)))
                if settings.watchThreshold != Settings.defaultWatchThreshold {
                    Button("Reset to 0.70") { settings.watchThreshold = Settings.defaultWatchThreshold }
                }
                SliderRow(
                    title: "Interval (s)", value: $settings.watchInterval,
                    range: Settings.watchIntervalRange, step: 0.5,
                    format: .number.precision(.fractionLength(1)))
                if settings.watchInterval != Settings.defaultWatchInterval {
                    Button("Reset to 2.5 s") { settings.watchInterval = Settings.defaultWatchInterval }
                }
            }
        } header: {
            Text("Watcher")
        } footer: {
            Text(
                "While a step card shows, a small frame is checked every few seconds. A warning appears only after two results in a row name the same mistake at this confidence or higher."
            )
        }

        WatchReadoutSection(log: env.watchLog)
    }
}

private struct SliderRow: View {
    let title: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let format: FloatingPointFormatStyle<Double>

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            LabeledContent(title) {
                Text(value, format: format).monospacedDigit()
            }
            Slider(value: $value, in: range, step: step) {
                Text(title)
            } minimumValueLabel: {
                Text(range.lowerBound, format: format)
            } maximumValueLabel: {
                Text(range.upperBound, format: format)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }
}

/// Newest first: outcome, mistake id, confidence, server latency / round trip.
private struct WatchReadoutSection: View {
    let log: WatchLog

    var body: some View {
        Section {
            if log.entries.isEmpty {
                Text("No results yet. Open a recipe and stay on a step card.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(log.entries) { entry in
                    WatchReadoutRow(entry: entry)
                }
                Button("Clear", role: .destructive) { log.clear() }
            }
        } header: {
            Text("Last \(WatchLog.capacity) Watch Results")
        } footer: {
            Text("Latency is the server's figure, then the round trip measured on the phone. Stale results were dropped without showing anything.")
        }
    }
}

private struct WatchReadoutRow: View {
    let entry: WatchLog.Entry

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
                .foregroundStyle(tint)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(entry.outcome.rawValue)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(tint)
                    if let id = entry.mistakeID {
                        Text(id)
                            .font(.subheadline.monospaced())
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                if let detail = entry.detail {
                    Text(detail).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            VStack(alignment: .trailing, spacing: 2) {
                if let confidence = entry.confidence {
                    Text(confidence, format: .number.precision(.fractionLength(2)))
                        .font(.subheadline.monospacedDigit())
                }
                Text(latency)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var latency: String {
        let server = entry.serverMs.map { "\($0)" } ?? "—"
        return "\(server) / \(entry.roundTripMs) ms"
    }

    private var symbol: String {
        switch entry.outcome {
        case .alert: "exclamationmark.triangle.fill"
        case .warn: "exclamationmark.circle"
        case .ok: "checkmark.circle"
        case .stale: "clock.arrow.circlepath"
        case .busy: "hourglass"
        case .error: "xmark.octagon"
        }
    }

    private var tint: Color {
        switch entry.outcome {
        case .alert, .warn: .orange
        case .ok: .green
        case .stale, .busy: .secondary
        case .error: .red
        }
    }
}

/// The watcher settings on their own, as a sheet over the cook-along.
struct WatcherSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    /// Medium keeps the lens visible while tuning; `-openWatcher` opens it full height for screenshots.
    @State private var detent: PresentationDetent = {
        #if DEBUG
            ProcessInfo.processInfo.arguments.contains("-openWatcher") ? .large : .medium
        #else
            .medium
        #endif
    }()

    var body: some View {
        NavigationStack {
            Form {
                WatcherSettingsSection()
            }
            .navigationTitle("Watcher")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large], selection: $detent)
    }
}

#Preview {
    WatcherSettingsSheet().environment(AppEnvironment.preview())
}
