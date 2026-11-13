import Foundation
import Testing

@testable import GhostChef

@Suite("Bundled fixture")
struct FixtureTests {
    @Test func draftDecodes() throws {
        let draft = try FixtureRecipe.loadDraft()
        #expect(draft.title == "Maki roll")
        #expect(!draft.transcript.isEmpty)
        #expect(draft.steps.map(\.idx) == Array(1...draft.steps.count))
    }

    @Test func demoMistakeIsExact() throws {
        let draft = try FixtureRecipe.loadDraft()
        let step3 = try #require(draft.steps.first { $0.idx == 3 })
        let w = try #require(step3.watchFors.first { $0.id == "rice_too_thick" })
        #expect(w.headline == "Too much rice")
        #expect(w.fix == "Spread thinner, 2cm nori free")
        #expect(
            w.spoken
                == "There's a bit too much rice — spread it thinner and leave two centimetres of nori at the top.")
    }

    @Test func wordLimits() throws {
        func words(_ s: String) -> Int { s.split(whereSeparator: \.isWhitespace).count }
        for step in try FixtureRecipe.loadDraft().steps {
            #expect(words(step.title) <= 4, "title: \(step.title)")
            #expect(words(step.keyLine) <= 8, "key_line: \(step.keyLine)")
            for w in step.watchFors {
                #expect(words(w.headline) <= 4, "headline: \(w.headline)")
                #expect(words(w.fix) <= 8, "fix: \(w.fix)")
            }
        }
    }

    @Test func loadsAsRecipeWithStableIDs() throws {
        let a = try FixtureRecipe.load()
        let b = try FixtureRecipe.load()
        #expect(a.status == .published)
        #expect(a.id == b.id)
        #expect(a.steps.map(\.id) == b.steps.map(\.id))
        #expect(Set(a.steps.map(\.id)).count == a.steps.count)
        #expect(a.steps.allSatisfy { $0.recipeID == a.id })
        #expect(UUID(uuidString: a.id) != nil)
    }

    @Test func everyStepHasABundledReferenceImage() throws {
        for step in try FixtureRecipe.load().steps {
            let url = try #require(step.refImageURL, "step \(step.idx) has no bundled image")
            let data = try Data(contentsOf: url)
            #expect(JPEGEncoder.pixelSize(of: data) != nil, "step \(step.idx): not a readable image")
        }
    }
}

@Suite("MockAPI")
struct MockAPITests {
    @Test func servesFixtureRecipe() async throws {
        let api = MockAPI.fixture()
        let list = try await api.recipes(status: .published)
        let summary = try #require(list.first)
        let recipe = try await api.recipe(id: summary.id)
        #expect(recipe.steps.count == summary.stepCount)
        #expect(try await api.recipes(status: .review).isEmpty)
        await #expect(throws: APIError.self) { try await api.recipe(id: "nope") }
    }

    @Test func scriptedCheckEchoesIDs() async throws {
        let api = MockAPI.fixture()
        await api.enqueueCheck(
            .success(
                CheckResponse(
                    requestID: "", stepID: "", verdict: .fix, mistakeID: "rice_too_thick",
                    headline: "Too much rice", fix: "Spread thinner, 2cm nori free", spoken: "…",
                    confidence: 0.9, latencyMs: 1, model: "mock")),
            .failure(APIError(status: 504, code: .modelTimeout, message: "slow", retryable: true)))

        let first = try await api.check(frame: Data(), stepID: "s3", requestID: "r1", sessionID: nil, capturedAt: nil)
        #expect(first.verdict == .fix)
        #expect(first.requestID == "r1")
        #expect(first.stepID == "s3")

        await #expect(throws: APIError.self) {
            try await api.check(frame: Data(), stepID: "s3", requestID: "r2", sessionID: nil, capturedAt: nil)
        }
        let third = try await api.check(frame: Data(), stepID: "s3", requestID: "r3", sessionID: nil, capturedAt: nil)
        #expect(third.verdict == .pass)

        let calls = await api.calls
        #expect(calls.filter { if case .check = $0 { true } else { false } }.count == 3)
    }

    @Test func healthIsLabelledAsFixture() async throws {
        let h = try await MockAPI.fixture().health()
        #expect(h.isFakeAI)
        #expect(h.isCompatibleContract)
    }
}

@Suite("Settings")
@MainActor
struct SettingsTests {
    func freshDefaults() -> UserDefaults {
        let name = "test.\(UUID().uuidString)"
        let d = UserDefaults(suiteName: name)!
        d.removePersistentDomain(forName: name)
        return d
    }

    @Test func overridesPersistAndApplyImmediately() {
        let defaults = freshDefaults()
        let settings = Settings(defaults: defaults)
        #expect(settings.watchThreshold == 0.7)

        settings.baseURLString = "http://10.0.0.5:8000"
        settings.demoKey = "k1"
        let config = Settings.apiConfig(defaults: defaults, bundle: .main)
        #expect(config.baseURL?.absoluteString == "http://10.0.0.5:8000")
        #expect(config.demoKey == "k1")

        settings.resetConnectionToBuildDefaults()
        let reset = Settings.apiConfig(defaults: defaults, bundle: .main)
        #expect(reset.baseURL?.absoluteString == Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String)
    }

    @Test func emptyURLIsNil() {
        let defaults = freshDefaults()
        defaults.set("   ", forKey: Settings.Key.baseURL)
        #expect(Settings.apiConfig(defaults: defaults, bundle: .main).baseURL == nil)
    }
}
