import Foundation

/// Everything the app asks of the backend (API-CONTRACT §2–§5).
/// `APIClient` talks HTTP; `MockAPI` serves the bundled fixture for previews, tests, and offline work.
protocol GhostChefAPI: Sendable {
    func health() async throws -> Health
    func recipes(status: RecipeStatus?) async throws -> [RecipeSummary]
    func recipe(id: String) async throws -> Recipe
    func createSession(recipeID: String, deviceLabel: String?) async throws -> SessionCreated
    @discardableResult
    func postEvent(
        sessionID: String, kind: SessionEventKind, stepID: String?, requestID: String?,
        payload: [String: JSONValue]
    ) async throws -> EventCreated
    func session(id: String) async throws -> SessionDetail
    func check(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> CheckResponse
    func watch(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> WatchResponse
    func liveToken(recipeID: String, sessionID: String?) async throws -> LiveTokenResponse

    // Chef mode (contract v2.0, IOS-08). The upload itself (TUS / PUT straight to Storage) is
    // `ChefUploader`'s job: it never goes through this API or carries the demo key.
    func createRecipe(title: String, chefName: String?, stepMarksS: [Double], consent: Bool) async throws -> RecipeUpload
    @discardableResult
    func processRecipe(id: String) async throws -> ProcessStarted
}

/// A fresh client-generated `request_id` (API-CONTRACT §1). Lowercase so it compares equal to
/// what a Python server echoes.
func newRequestID() -> String {
    UUID().uuidString.lowercased()
}
