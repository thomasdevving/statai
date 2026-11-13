import SwiftUI

/// Recipes is the home screen; Settings opens as a sheet from its toolbar.
struct RootView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var showingSettings = false

    var body: some View {
        NavigationStack {
            RecipeListView()
                .navigationDestination(for: RecipeSummary.self) { summary in
                    CookView(summary: summary)
                }
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Settings", systemImage: "gearshape") { showingSettings = true }
                    }
                }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView()
        }
    }
}

#Preview {
    RootView().environment(AppEnvironment.preview())
}
