import Foundation

// API-CONTRACT §5 (live token), §2 (health), §1.1 (error envelope).

/// The `config` block of `GET /live-token`. When the token is `locked`, the client must not
/// send its own config; this copy is for logging and display.
struct LiveConfig: Codable, Sendable, Hashable {
    var systemInstruction: String
    var responseModalities: [String]
    var voice: String?
    var tools: [JSONValue]
    var sessionResumption: Bool
}

/// `GET /live-token`.
struct LiveTokenResponse: Codable, Sendable, Hashable {
    var token: String
    var expiresAt: Date
    var newSessionExpiresAt: Date
    var model: String
    var apiVersion: String
    var locked: Bool
    var config: LiveConfig
}

/// `GET /health`.
struct Health: Codable, Sendable, Hashable {
    var status: String
    var contractVersion: String
    var aiMode: String
    var storage: String

    /// True when the server answers checks with fake AI. Shown as a warning so nobody demos it by accident.
    var isFakeAI: Bool { aiMode != "gemini" }

    /// Major contract version this app is built against (docs/API-CONTRACT.md).
    static let supportedContractMajor = "2"

    var isCompatibleContract: Bool {
        contractVersion.split(separator: ".").first.map(String.init) == Self.supportedContractMajor
    }
}

enum APIErrorCode: String, LenientStringEnum, CaseIterable {
    case unauthorized
    case notFound = "not_found"
    case recipeNotReady = "recipe_not_ready"
    case uploadMissing = "upload_missing"
    case payloadTooLarge = "payload_too_large"
    case unsupportedMedia = "unsupported_media"
    case validationError = "validation_error"
    case quotaExhausted = "quota_exhausted"
    case modelUnavailable = "model_unavailable"
    case modelTimeout = "model_timeout"
    case `internal`
    case unknown

    static var unknownCase: Self { .unknown }
}

/// Every non-2xx body: `{ "error": { code, message, retryable, request_id } }`.
struct APIErrorBody: Codable, Sendable, Hashable {
    struct Detail: Codable, Sendable, Hashable {
        var code: APIErrorCode
        var message: String
        var retryable: Bool
        var requestID: String?

        enum CodingKeys: String, CodingKey {
            case code, message, retryable
            case requestID = "requestId"
        }
    }

    var error: Detail
}
