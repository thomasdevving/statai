import SwiftUI

/// The first screen (IOS-08.1): Cook (follow a recipe) or Chef (record one through the glasses).
/// The last choice is remembered and reopened; Settings is reachable from every screen.
struct ModePickerView: View {
    @Environment(AppEnvironment.self) private var env
    var open: (Settings.AppMode) -> Void

    var body: some View {
        VStack(spacing: 16) {
            Spacer(minLength: 0)
            modeButton(
                .cook, title: "Cook", subtitle: "Follow a chef's recipe hands-free",
                systemImage: "fork.knife", tint: .accentColor)
            modeButton(
                .chef, title: "Chef", subtitle: "Record a recipe through the glasses",
                systemImage: "record.circle", tint: .red)
            Spacer(minLength: 0)
        }
        .padding(20)
        .navigationTitle("Echo")
    }

    private func modeButton(
        _ mode: Settings.AppMode, title: String, subtitle: String, systemImage: String, tint: Color
    ) -> some View {
        Button {
            env.settings.lastAppMode = mode
            open(mode)
        } label: {
            HStack(spacing: 16) {
                Image(systemName: systemImage)
                    .font(.system(size: 34, weight: .semibold))
                    .frame(width: 56)
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.title.bold())
                    Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
                if env.settings.lastAppMode == mode {
                    Text("Last used").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, minHeight: 120)
            .background(tint.opacity(0.12), in: .rect(cornerRadius: 24))
            .foregroundStyle(.primary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(title): \(subtitle)")
    }
}
