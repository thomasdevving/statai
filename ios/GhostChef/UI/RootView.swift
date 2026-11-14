import SwiftUI

/// Root (IOS-08.1): the mode picker, then Cook (recipes → cook-along) or Chef (record a take).
/// The last mode opens on launch, one step back from the picker. Settings opens as a sheet from
/// every screen's toolbar.
struct RootView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var path = NavigationPath()
    @State private var didRestoreMode = false
    /// Debug builds accept `-openSettings` as a launch argument, for screenshots and UI checks.
    @State private var showingSettings = {
        #if DEBUG
            ProcessInfo.processInfo.arguments.contains("-openSettings")
        #else
            false
        #endif
    }()

    var body: some View {
        NavigationStack(path: $path) {
            ModePickerView { mode in path.append(mode) }
                .toolbar { settingsButton }
                .navigationDestination(for: Settings.AppMode.self) { mode in
                    switch mode {
                    case .cook:
                        RecipeListView().toolbar { settingsButton }
                    case .chef:
                        ChefRecordView().toolbar { settingsButton }
                    }
                }
                .navigationDestination(for: RecipeSummary.self) { summary in
                    CookView(summary: summary)
                }
        }
        .onAppear {
            // Reopen the last mode once per launch; Back returns to the picker.
            guard !didRestoreMode else { return }
            didRestoreMode = true
            if let last = env.settings.lastAppMode { path.append(last) }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView()
        }
    }

    @ToolbarContentBuilder
    private var settingsButton: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button("Settings", systemImage: "gearshape") { showingSettings = true }
        }
    }
}

#Preview {
    RootView().environment(AppEnvironment.preview())
}
