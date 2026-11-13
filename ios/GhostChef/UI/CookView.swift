import SwiftUI

/// Placeholder for the cook-along (IOS-03 replaces it): loads the recipe and shows step 1's
/// title, reference image, and key line, laid out like the lens step card.
struct CookView: View {
    let summary: RecipeSummary

    @Environment(AppEnvironment.self) private var env
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var recipe: Recipe?
    @State private var error: String?

    var body: some View {
        ScrollView {
            if let step = recipe?.steps.first, let recipe {
                stepCard(step, of: recipe.steps.count)
                    .transition(.opacity)
            } else if let error {
                ContentUnavailableView {
                    Label("Couldn't open this recipe", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                } actions: {
                    Button("Try Again") { Task { await load() } }.buttonStyle(.borderedProminent)
                }
                .padding(.top, 80)
            } else if recipe != nil {
                ContentUnavailableView(
                    "This recipe has no steps", systemImage: "list.bullet",
                    description: Text("It may still be processing."))
                .padding(.top, 80)
            } else {
                ProgressView().padding(.top, 120)
            }
        }
        .animation(Motion.standard(reduceMotion: reduceMotion), value: recipe)
        .navigationTitle(summary.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func stepCard(_ step: Step, of total: Int) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Step \(step.idx) of \(total)")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)
                .tracking(0.6)

            Text(step.title)
                .font(.largeTitle.weight(.bold))
                .tracking(-0.4)

            ReferenceImage(url: step.refImageURL)
                .aspectRatio(3 / 4, contentMode: .fit)
                .frame(maxWidth: .infinity)

            Text(step.keyLine)
                .font(.title3.weight(.medium))

            Label("Cook-along is not built yet. This screen previews step 1.", systemImage: "hammer")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .padding(.top, 8)
        }
        .padding(20)
    }

    private func load() async {
        error = nil
        do {
            recipe = try await env.api.recipe(id: summary.id)
        } catch is CancellationError {
        } catch {
            self.error = error.localizedDescription
        }
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
