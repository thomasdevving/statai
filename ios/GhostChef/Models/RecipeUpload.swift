import Foundation

// API-CONTRACT §2 (v2.0): creating a recipe from a Chef-mode take (IOS-08.2).

/// `POST /recipes` request body.
struct RecipeCreate: Codable, Sendable, Hashable {
    var title: String
    var chefName: String?
    /// Seconds from the start of the video at which the chef marked a new step. Ascending.
    var stepMarksS: [Double]
    /// Must be `true`: everyone in the recording agreed to it being processed by Gemini.
    var consent: Bool
}

/// `POST /recipes` → `201`. The video never goes through FastAPI: the client uploads it straight
/// to Storage with `upload_url` (simple `PUT`) or `resumable_endpoint` (TUS, Supabase only).
struct RecipeUpload: Codable, Sendable, Hashable {
    var recipeID: String
    var status: RecipeStatus
    var uploadURL: URL
    var uploadToken: String
    var bucket: String
    var objectPath: String
    /// `null` when the backend runs with `STORAGE=memory`: then only the simple `PUT` works.
    var resumableEndpoint: URL?
    var uploadExpiresAt: Date

    enum CodingKeys: String, CodingKey {
        case recipeID = "recipeId"
        case status
        case uploadURL = "uploadUrl"
        case uploadToken, bucket, objectPath, resumableEndpoint, uploadExpiresAt
    }
}

/// `POST /recipes/{id}/process` → `202`.
struct ProcessStarted: Codable, Sendable, Hashable {
    var recipeID: String
    var status: RecipeStatus

    enum CodingKeys: String, CodingKey {
        case recipeID = "recipeId"
        case status
    }
}
