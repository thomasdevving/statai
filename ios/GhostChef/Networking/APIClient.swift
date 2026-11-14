import Foundation

/// Where to send requests. Read fresh for every request, so Settings changes apply without a restart.
struct APIConfig: Sendable, Equatable {
    var baseURL: URL?
    var demoKey: String
}

/// HTTP implementation of `GhostChefAPI` (API-CONTRACT §1–§5).
final class APIClient: GhostChefAPI {
    /// Request timeouts in seconds (IOS-01.4). The server budgets are 8 s and 3.5 s.
    enum Timeout {
        static let check: TimeInterval = 10
        static let watch: TimeInterval = 4
        static let standard: TimeInterval = 10
    }

    static let demoKeyHeader = "X-Demo-Key"

    private let session: URLSession
    private let config: @Sendable () -> APIConfig

    init(session: URLSession = .shared, config: @escaping @Sendable () -> APIConfig) {
        self.session = session
        self.config = config
    }

    // MARK: - GhostChefAPI

    func health() async throws -> Health {
        try await send(try makeRequest("GET", path: "health"))
    }

    func recipes(status: RecipeStatus?) async throws -> [RecipeSummary] {
        let query = status.map { [URLQueryItem(name: "status", value: $0.rawValue)] } ?? []
        let list: RecipeList = try await send(try makeRequest("GET", path: "recipes", query: query))
        return list.recipes
    }

    func recipe(id: String) async throws -> Recipe {
        try await send(try makeRequest("GET", path: "recipes/\(id)"))
    }

    func createSession(recipeID: String, deviceLabel: String?) async throws -> SessionCreated {
        let body = CreateSessionBody(recipeID: recipeID, client: "ios", deviceLabel: deviceLabel)
        return try await send(try makeRequest("POST", path: "sessions", json: body))
    }

    @discardableResult
    func postEvent(
        sessionID: String, kind: SessionEventKind, stepID: String?, requestID: String?,
        payload: [String: JSONValue]
    ) async throws -> EventCreated {
        precondition(!kind.isServerRecorded, "Clients never post server-recorded event kinds (§4)")
        let body = PostEventBody(kind: kind, stepID: stepID, requestID: requestID, payload: payload)
        return try await send(try makeRequest("POST", path: "sessions/\(sessionID)/events", json: body))
    }

    func session(id: String) async throws -> SessionDetail {
        try await send(try makeRequest("GET", path: "sessions/\(id)"))
    }

    func check(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> CheckResponse {
        try await send(
            try makeFrameRequest(
                path: "check", frame: frame, stepID: stepID, requestID: requestID,
                sessionID: sessionID, capturedAt: capturedAt, timeout: Timeout.check))
    }

    func watch(
        frame: Data, stepID: String, requestID: String, sessionID: String?, capturedAt: Date?
    ) async throws -> WatchResponse {
        try await send(
            try makeFrameRequest(
                path: "watch", frame: frame, stepID: stepID, requestID: requestID,
                sessionID: sessionID, capturedAt: capturedAt, timeout: Timeout.watch))
    }

    func liveToken(recipeID: String, sessionID: String?) async throws -> LiveTokenResponse {
        var query = [URLQueryItem(name: "recipe_id", value: recipeID)]
        if let sessionID { query.append(URLQueryItem(name: "session_id", value: sessionID)) }
        return try await send(try makeRequest("GET", path: "live-token", query: query))
    }

    func createRecipe(title: String, chefName: String?, stepMarksS: [Double], consent: Bool) async throws -> RecipeUpload {
        let body = RecipeCreate(title: title, chefName: chefName, stepMarksS: stepMarksS, consent: consent)
        return try await send(try makeRequest("POST", path: "recipes", json: body))
    }

    @discardableResult
    func processRecipe(id: String) async throws -> ProcessStarted {
        try await send(try makeRequest("POST", path: "recipes/\(id)/process"))
    }

    // MARK: - Request building (internal for tests)

    func makeRequest(
        _ method: String, path: String, query: [URLQueryItem] = [],
        timeout: TimeInterval = Timeout.standard
    ) throws -> URLRequest {
        let current = config()
        guard let base = current.baseURL, base.scheme != nil, base.host() != nil else {
            throw APIError.invalidConfiguration(
                message: "Set the backend URL in Settings (e.g. http://192.168.1.20:8000).")
        }
        var url = base.appending(path: path)
        if !query.isEmpty { url.append(queryItems: query) }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if path != "health" {
            request.setValue(current.demoKey, forHTTPHeaderField: Self.demoKeyHeader)
        }
        return request
    }

    func makeRequest(_ method: String, path: String, json body: some Encodable) throws -> URLRequest {
        var request = try makeRequest(method, path: path)
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONCoding.encoder.encode(body)
        return request
    }

    func makeFrameRequest(
        path: String, frame: Data, stepID: String, requestID: String, sessionID: String?,
        capturedAt: Date?, timeout: TimeInterval, boundary: String? = nil
    ) throws -> URLRequest {
        var request = try makeRequest("POST", path: path, timeout: timeout)
        var form = boundary.map { MultipartFormData(boundary: $0) } ?? MultipartFormData()
        form.addFile(name: "frame", filename: "frame.jpg", mimeType: "image/jpeg", data: frame)
        form.addField(name: "step_id", value: stepID)
        form.addField(name: "request_id", value: requestID)
        if let sessionID { form.addField(name: "session_id", value: sessionID) }
        if let capturedAt { form.addField(name: "captured_at", value: ISO8601.string(from: capturedAt)) }
        request.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = form.finalized()
        return request
    }

    // MARK: - Sending

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let error as URLError {
            throw APIError.network(message: error.localizedDescription, timedOut: error.code == .timedOut)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw APIError.network(message: error.localizedDescription, timedOut: false)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.network(message: "Not an HTTP response", timedOut: false)
        }
        guard (200..<300).contains(http.statusCode) else {
            throw Self.decodeError(status: http.statusCode, data: data)
        }
        do {
            return try JSONCoding.decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(message: String(describing: error))
        }
    }

    /// Decodes the §1.1 envelope; falls back to the status code when the body is not one.
    static func decodeError(status: Int, data: Data) -> APIError {
        if let body = try? JSONCoding.decoder.decode(APIErrorBody.self, from: data) {
            return .server(
                status: status, code: body.error.code, message: body.error.message,
                retryable: body.error.retryable, requestID: body.error.requestID)
        }
        let code: APIErrorCode =
            switch status {
            case 401: .unauthorized
            case 404: .notFound
            case 409: .recipeNotReady
            case 413: .payloadTooLarge
            case 415: .unsupportedMedia
            case 422: .validationError
            case 429: .quotaExhausted
            case 503: .modelUnavailable
            case 504: .modelTimeout
            case 500...: .internal
            default: .unknown
            }
        let text = String(data: data.prefix(200), encoding: .utf8) ?? ""
        return .server(
            status: status, code: code,
            message: text.isEmpty ? HTTPURLResponse.localizedString(forStatusCode: status) : text,
            retryable: status == 429 || status >= 500, requestID: nil)
    }
}
