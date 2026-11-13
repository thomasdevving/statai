import Foundation

/// The fixture file is a `RecipeDraft` (API-CONTRACT §7, §8): no ids, no URLs.
struct RecipeDraft: Codable, Sendable, Hashable {
    struct StepSpec: Codable, Sendable, Hashable {
        var idx: Int
        var title: String
        var keyLine: String
        var instruction: String
        var chefQuote: String?
        var timestampS: Double
        var clipStartS: Double?
        var clipEndS: Double?
        var successCriteria: [String]
        var watchFors: [WatchFor]
        var timerS: Int?
    }

    var title: String
    var transcript: String
    var steps: [StepSpec]
}

/// Loads the bundled fixture as a full `Recipe`, for previews, tests, and the offline data source.
/// Integrated runs must load real data from the API (API-CONTRACT §8).
enum FixtureRecipe {
    static let resourceName = "sushi_recipe"
    static let subdirectory = "Fixtures"

    enum LoadError: Error, Equatable {
        case missing
    }

    static func loadDraft(bundle: Bundle = .main) throws -> RecipeDraft {
        guard
            let url = bundle.url(
                forResource: resourceName, withExtension: "json", subdirectory: subdirectory)
        else { throw LoadError.missing }
        let data = try Data(contentsOf: url)
        return try JSONCoding.decoder.decode(RecipeDraft.self, from: data)
    }

    /// Turns the draft into a `Recipe`. IDs are deterministic (derived from `idx`) so previews and
    /// tests are stable across launches. Reference images resolve to `Fixtures/images/step-<idx>.jpg`
    /// in the bundle when present.
    static func load(bundle: Bundle = .main) throws -> Recipe {
        let draft = try loadDraft(bundle: bundle)
        let recipeID = fixtureID(0)
        let steps = draft.steps.sorted { $0.idx < $1.idx }.map { spec in
            Step(
                id: fixtureID(spec.idx),
                recipeID: recipeID,
                idx: spec.idx,
                title: spec.title,
                keyLine: spec.keyLine,
                instruction: spec.instruction,
                chefQuote: spec.chefQuote,
                timestampS: spec.timestampS,
                clipStartS: spec.clipStartS,
                clipEndS: spec.clipEndS,
                successCriteria: spec.successCriteria,
                watchFors: spec.watchFors,
                refImageURL: bundle.url(
                    forResource: "step-\(spec.idx)", withExtension: "jpg",
                    subdirectory: "\(subdirectory)/images"),
                clipURL: nil,
                timerS: spec.timerS
            )
        }
        return Recipe(
            id: recipeID, title: draft.title, chefName: "Fixture chef", status: .published,
            transcript: draft.transcript, steps: steps)
    }

    /// `00000000-0000-4000-8000-0000000000NN`: a valid v4-shaped UUID string per index.
    static func fixtureID(_ n: Int) -> String {
        String(format: "00000000-0000-4000-8000-%012d", n)
    }
}
