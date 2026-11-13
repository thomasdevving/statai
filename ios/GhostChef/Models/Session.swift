import Foundation

// API-CONTRACT §4: sessions and events.

enum SessionEventKind: String, LenientStringEnum, CaseIterable {
    // Recorded by the server inside /check and /watch. Clients never post these.
    case checkPass = "check_pass"
    case checkFix = "check_fix"
    case checkUnsure = "check_unsure"
    case watchWarn = "watch_warn"
    // Posted by the client.
    case stepChange = "step_change"
    case question
    case warningShown = "warning_shown"
    case warningDismissed = "warning_dismissed"
    case showMe = "show_me"
    case clientError = "client_error"
    case sessionEnd = "session_end"
    case unknown

    static var unknownCase: Self { .unknown }

    /// Kinds the server records itself (§4 "Clients never post the server-recorded kinds").
    var isServerRecorded: Bool {
        switch self {
        case .checkPass, .checkFix, .checkUnsure, .watchWarn: true
        default: false
        }
    }
}

/// `POST /sessions` 201 body.
struct SessionCreated: Codable, Sendable, Hashable {
    var sessionID: String
    var startedAt: Date

    enum CodingKeys: String, CodingKey {
        case startedAt
        case sessionID = "sessionId"
    }
}

/// `POST /sessions/{id}/events` 201 body.
struct EventCreated: Codable, Sendable, Hashable {
    var eventID: String

    enum CodingKeys: String, CodingKey {
        case eventID = "eventId"
    }
}

struct SessionEvent: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var kind: SessionEventKind
    var stepID: String?
    var requestID: String?
    var payload: [String: JSONValue]
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, kind, payload, createdAt
        case stepID = "stepId"
        case requestID = "requestId"
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        kind = try c.decode(SessionEventKind.self, forKey: .kind)
        stepID = try c.decodeIfPresent(String.self, forKey: .stepID)
        requestID = try c.decodeIfPresent(String.self, forKey: .requestID)
        payload = try c.decodeIfPresent([String: JSONValue].self, forKey: .payload) ?? [:]
        createdAt = try c.decode(Date.self, forKey: .createdAt)
    }
}

/// The `summary` block of `GET /sessions/{id}`; feeds the Done screen.
struct SessionSummary: Codable, Sendable, Hashable {
    var stepsTotal: Int
    var stepsPassedFirstTry: Int
    var fixesCaught: Int
    var warnings: Int
    var questions: Int
}

/// `GET /sessions/{id}`.
struct SessionDetail: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var recipeID: String
    var client: String
    var startedAt: Date
    var finishedAt: Date?
    var events: [SessionEvent]
    var summary: SessionSummary?

    enum CodingKeys: String, CodingKey {
        case id, client, startedAt, finishedAt, events, summary
        case recipeID = "recipeId"
    }
}

// MARK: - Request bodies

struct CreateSessionBody: Encodable, Sendable {
    var recipeID: String
    var client: String
    var deviceLabel: String?
}

struct PostEventBody: Encodable, Sendable {
    var kind: SessionEventKind
    var stepID: String?
    var requestID: String?
    var payload: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case kind, stepID, requestID, payload
    }

    // Send explicit nulls: the contract shows `"step_id": "uuid or null"`.
    func encode(to encoder: any Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(kind, forKey: .kind)
        try c.encode(stepID, forKey: .stepID)
        try c.encode(requestID, forKey: .requestID)
        try c.encode(payload, forKey: .payload)
    }
}
