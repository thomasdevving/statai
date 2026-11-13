import Foundation

// API-CONTRACT §3: /check and /watch responses.

enum Verdict: String, LenientStringEnum, CaseIterable {
    case pass, fix, unsure, unknown
    static var unknownCase: Self { .unknown }
}

enum WatchStatus: String, LenientStringEnum, CaseIterable {
    case ok, warn, unknown
    static var unknownCase: Self { .unknown }
}

/// `POST /check` 200 body.
struct CheckResponse: Codable, Sendable, Hashable {
    var requestID: String
    var stepID: String
    var verdict: Verdict
    var mistakeID: String?
    var headline: String
    var fix: String
    var spoken: String
    var confidence: Double
    var latencyMs: Int?
    var model: String?

    enum CodingKeys: String, CodingKey {
        case verdict, headline, fix, spoken, confidence, latencyMs, model
        case requestID = "requestId"
        case stepID = "stepId"
        case mistakeID = "mistakeId"
    }
}

/// `POST /watch` 200 body.
struct WatchResponse: Codable, Sendable, Hashable {
    var requestID: String
    var stepID: String
    var status: WatchStatus
    var mistakeID: String?
    var headline: String
    var fix: String
    var spoken: String
    var confidence: Double
    var latencyMs: Int?
    var model: String?

    enum CodingKeys: String, CodingKey {
        case status, headline, fix, spoken, confidence, latencyMs, model
        case requestID = "requestId"
        case stepID = "stepId"
        case mistakeID = "mistakeId"
    }
}
