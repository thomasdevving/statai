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
    /// Client-posted events, in order, for assertions.
    private(set) var postedEvents: [PostedEvent] = []
    /// Verdicts served per session, in order; feeds the summary like the backend's `summarize`.
    private var servedVerdicts: [(sessionID: String?, stepID: String, verdict: Verdict)] = []
    /// When true, `/check` waits until `releaseChecks()` (tests of slow and stale responses).
    private var holdChecks = false
    private var heldChecks: [CheckedContinuation<Void, Never>] = []
    /// Artificial latency for previews, in seconds.
    var delay: Double
    /// With an empty script, answer like the backend's fake AI (`ghostchef_ai.fake`): per step,
    /// odd calls → `fix` with the step's first watch-for, even calls → `pass`. Lets the bundled
    /// fixture show the whole fix → re-check → pass loop offline. Off: always `pass`.
    private let mimicFakeAI: Bool
    private var checkCountByStep: [String: Int] = [:]

    init(recipe: Recipe, delay: Double = 0, mimicFakeAI: Bool = false) {
        self.recipe = recipe
        self.delay = delay
        self.mimicFakeAI = mimicFakeAI
    }

    /// Uses the bundled fixture; falls back to an empty recipe list if it cannot be read.
    static func fixture(bundle: Bundle = .main, delay: Double = 0, mimicFakeAI: Bool = false) -> MockAPI {
        let recipe =
            (try? FixtureRecipe.load(bundle: bundle))
            ?? Recipe(id: FixtureRecipe.fixtureID(0), title: "Fixture missing", status: .failed, steps: [])
        return MockAPI(recipe: recipe, delay: delay, mimicFakeAI: mimicFakeAI)
    }

    // MARK: Scripting

    func enqueueCheck(_ results: Result<CheckResponse, APIError>...) { checkScript += results }
    func enqueueWatch(_ results: Result<WatchResponse, APIError>...) { watchScript += results }
    func setDelay(_ seconds: Double) { delay = seconds }
    func setHoldChecks(_ hold: Bool) { holdChecks = hold }
    /// Lets every held `/check` call answer.
    func releaseChecks() {
        let held = heldChecks
        heldChecks = []
        held.forEach { $0.resume() }
    }
    var heldCheckCount: Int { heldChecks.count }

    struct PostedEvent: Sendable, Equatable {
        var sessionID: String
        var kind: SessionEventKind
        var stepID: String?
        var payload: [String: JSONValue]
    }

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
        checkCountByStep = [:]
        return SessionCreated(sessionID: newRequestID(), startedAt: .now)
    }

    @discardableResult
    func postEvent(
        sessionID: String, kind: SessionEventKind, stepID: String?, requestID: String?,
        payload: [String: JSONValue]
    ) async throws -> EventCreated {
        calls.append(.postEvent(kind))
        postedEvents.append(
            PostedEvent(sessionID: sessionID, kind: kind, stepID: stepID, payload: payload))
        let id = newRequestID()
        return EventCreated(eventID: id)
    }

    func session(id: String) async throws -> SessionDetail {
        calls.append(.session(id))
        return SessionDetail(
            id: id, recipeID: recipe.id, client: "ios", startedAt: .now, finishedAt: nil,
            events: events,
            summary: summary(sessionID: id))
    }

    /// Mirrors backend `summarize`: a step passed first try when its first pass/fix verdict is a
    /// pass (`unsure` is not a verdict); every fix counts as caught.
    private func summary(sessionID: String) -> SessionSummary {
        var first: [String: Verdict] = [:]
        var fixes = 0
        for served in servedVerdicts where served.sessionID == sessionID {
            guard served.verdict == .pass || served.verdict == .fix else { continue }
            if served.verdict == .fix { fixes += 1 }
            if first[served.stepID] == nil { first[served.stepID] = served.verdict }
        }
        return SessionSummary(
            stepsTotal: recipe.steps.count,
            stepsPassedFirstTry: first.values.filter { $0 == .pass }.count, fixesCaught: fixes,
            warnings: 0,
            questions: postedEvents.filter { $0.sessionID == sessionID && $0.kind == .question }.count)
    }

    func check(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> CheckResponse {
        calls.append(.check(stepID: stepID, requestID: requestID))
        await pause()
        if holdChecks {
            await withCheckedContinuation { heldChecks.append($0) }
        }
        if !checkScript.isEmpty {
            var result = try checkScript.removeFirst().get()
            result.requestID = requestID
            result.stepID = stepID
            servedVerdicts.append((sessionID, stepID, result.verdict))
            return result
        }
        let count = (checkCountByStep[stepID] ?? 0) + 1
        checkCountByStep[stepID] = count
        if mimicFakeAI, count % 2 == 1,
            let w = recipe.steps.first(where: { $0.id == stepID })?.watchFors.first
        {
            servedVerdicts.append((sessionID, stepID, .fix))
            return CheckResponse(
                requestID: requestID, stepID: stepID, verdict: .fix, mistakeID: w.id,
                headline: w.headline, fix: w.fix, spoken: w.spoken, confidence: 0.9,
                latencyMs: Int(delay * 1000), model: "mock")
        }
        servedVerdicts.append((sessionID, stepID, .pass))
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
