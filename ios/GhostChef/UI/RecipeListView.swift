import SwiftUI

/// Published recipes from `GET /recipes?status=published`, with pull to refresh and clear
/// loading, error, and empty states.
struct RecipeListView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    enum LoadState: Equatable {
        case loading
        case loaded([RecipeSummary])
        case failed(String)
    }

    @State private var state: LoadState = .loading

    var body: some View {
        content
            .navigationTitle("Recipes")
            .animation(Motion.standard(reduceMotion: reduceMotion), value: state)
            .safeAreaInset(edge: .top, spacing: 0) {
                if env.isUsingFixture {
                    StatusChip(
                        title: "Bundled fixture — not live data", systemImage: "shippingbox",
                        tone: .warning
                    )
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity)
                }
            }
            .task(id: env.settings.dataSource) { await load() }
    }

    @ViewBuilder
    private var content: some View {
        switch state {
        case .loading:
            ProgressView("Loading recipes…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let message):
            ContentUnavailableView {
                Label("Couldn't load recipes", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") { Task { await load() } }
                    .buttonStyle(.borderedProminent)
            }
        case .loaded(let recipes) where recipes.isEmpty:
            ScrollView {
                ContentUnavailableView(
                    "No published recipes",
                    systemImage: "fork.knife",
                    description: Text("Publish a recipe in the chef studio, then pull down to refresh.")
                )
                .padding(.top, 80)
            }
            .refreshable { await load() }
        case .loaded(let recipes):
            List(recipes) { recipe in
                NavigationLink(value: recipe) {
                    RecipeRow(recipe: recipe)
                }
            }
            .listStyle(.insetGrouped)
            .refreshable { await load() }
        }
    }

    private func load() async {
        if case .loaded = state {} else { state = .loading }
        do {
            let recipes = try await env.api.recipes(status: .published)
            state = .loaded(recipes)
        } catch is CancellationError {
            // View went away or the data source changed; the next task reloads.
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

private struct RecipeRow: View {
    let recipe: RecipeSummary

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "fork.knife")
                .font(.title3)
                .foregroundStyle(.tint)
                .frame(width: 44, height: 44)
                .background(.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(recipe.title)
                    .font(.headline)
                HStack(spacing: 6) {
                    if let chef = recipe.chefName, !chef.isEmpty {
                        Text(chef)
                        Text("·").accessibilityHidden(true)
                    }
                    Text("^[\(recipe.stepCount) step](inflect: true)")
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

#Preview("Fixture") {
    NavigationStack { RecipeListView() }
        .environment(AppEnvironment.preview())
}
