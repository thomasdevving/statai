import Foundation

/// Offline `GhostChefAPI` backed by the bundled fixture, for previews, unit tests, and working
/// without a backend. Check and watch results are scriptable; when the script is empty it answers
/// `pass` / `ok`. Anything it returns is fixture data and must be labelled as such in the UI.
actor MockAPI: GhostChefAPI {
    enum Call: Sendable, Equatable {
        case health, recipes, recipe(String), createSession(String), postEvent(SessionEventKind)
        case session(String), check(stepID: String, requestID: String)
        case watch(stepID: String, requestID: String), liveToken(String)
    }

    private let recipe: Recipe
    private var checkScript: [Result<CheckResponse, APIError>] = []
    private var watchScript: [Result<WatchResponse, APIError>] = []
    private var events: [SessionEvent] = []
    private(set) var calls: [Call] = []
    /// Artificial latency for previews, in seconds.
    var delay: Double

    init(recipe: Recipe, delay: Double = 0) {
        self.recipe = recipe
        self.delay = delay
    }

    /// Uses the bundled fixture; falls back to an empty recipe list if it cannot be read.
    static func fixture(bundle: Bundle = .main, delay: Double = 0) -> MockAPI {
        let recipe =
            (try? FixtureRecipe.load(bundle: bundle))
            ?? Recipe(id: FixtureRecipe.fixtureID(0), title: "Fixture missing", status: .failed, steps: [])
        return MockAPI(recipe: recipe, delay: delay)
    }

    // MARK: Scripting

    func enqueueCheck(_ results: Result<CheckResponse, APIError>...) { checkScript += results }
    func enqueueWatch(_ results: Result<WatchResponse, APIError>...) { watchScript += results }
    func setDelay(_ seconds: Double) { delay = seconds }

    // MARK: GhostChefAPI

    func health() async throws -> Health {
        calls.append(.health)
        await pause()
        return Health(status: "ok", contractVersion: "2.0", aiMode: "fixture", storage: "bundle")
    }

    func recipes(status: RecipeStatus?) async throws -> [RecipeSummary] {
        calls.append(.recipes)
        await pause()
        guard status == nil || status == recipe.status else { return [] }
        return [recipe.summary]
    }

    func recipe(id: String) async throws -> Recipe {
        calls.append(.recipe(id))
        await pause()
        guard id == recipe.id else {
            throw APIError(status: 404, code: .notFound, message: "Unknown recipe", retryable: false)
        }
        return recipe
    }

    func createSession(recipeID: String, deviceLabel: String?) async throws -> SessionCreated {
        calls.append(.createSession(recipeID))
        events = []
        return SessionCreated(sessionID: newRequestID(), startedAt: .now)
    }

    @discardableResult
    func postEvent(
        sessionID: String, kind: SessionEventKind, stepID: String?, requestID: String?,
        payload: [String: JSONValue]
    ) async throws -> EventCreated {
        calls.append(.postEvent(kind))
        let id = newRequestID()
        return EventCreated(eventID: id)
    }

    func session(id: String) async throws -> SessionDetail {
        calls.append(.session(id))
        return SessionDetail(
            id: id, recipeID: recipe.id, client: "ios", startedAt: .now, finishedAt: nil,
            events: events,
            summary: SessionSummary(
                stepsTotal: recipe.steps.count, stepsPassedFirstTry: 0, fixesCaught: 0, warnings: 0,
                questions: 0))
    }

    func check(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> CheckResponse {
        calls.append(.check(stepID: stepID, requestID: requestID))
        await pause()
        if !checkScript.isEmpty {
            var result = try checkScript.removeFirst().get()
            result.requestID = requestID
            result.stepID = stepID
            return result
        }
        return CheckResponse(
            requestID: requestID, stepID: stepID, verdict: .pass, mistakeID: nil,
            headline: "Looks right", fix: "", spoken: "That looks right.", confidence: 0.9,
            latencyMs: Int(delay * 1000), model: "mock")
    }

    func watch(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> WatchResponse {
        calls.append(.watch(stepID: stepID, requestID: requestID))
        await pause()
        if !watchScript.isEmpty {
            var result = try watchScript.removeFirst().get()
            result.requestID = requestID
            result.stepID = stepID
            return result
        }
        return WatchResponse(
            requestID: requestID, stepID: stepID, status: .ok, mistakeID: nil, headline: "",
            fix: "", spoken: "", confidence: 0, latencyMs: Int(delay * 1000), model: "mock")
    }

    func liveToken(recipeID: String, sessionID: String?) async throws -> LiveTokenResponse {
        calls.append(.liveToken(recipeID))
        throw APIError(
            status: 503, code: .modelUnavailable,
            message: "Voice is not available with the bundled fixture", retryable: false)
    }

    private func pause() async {
        guard delay > 0 else { return }
        try? await Task.sleep(for: .seconds(delay))
    }
}
