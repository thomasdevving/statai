import Foundation

/// Every failure `APIClient` can throw.
enum APIError: Error, Sendable, Equatable {
    /// A non-2xx response. `code`/`message`/`retryable` come from the error envelope (§1.1) when the
    /// body has one; otherwise they are derived from the status.
    case server(status: Int, code: APIErrorCode, message: String, retryable: Bool, requestID: String?)
    /// The request never got an HTTP response: offline, DNS, refused connection, client timeout.
    case network(message: String, timedOut: Bool)
    /// A 2xx body that does not match the contract.
    case decoding(message: String)
    /// Base URL missing or malformed in Settings.
    case invalidConfiguration(message: String)

    /// Convenience matching the batch spec's `APIError(status:code:message:retryable:)` shape.
    init(status: Int, code: APIErrorCode, message: String, retryable: Bool, requestID: String? = nil) {
        self = .server(
            status: status, code: code, message: message, retryable: retryable, requestID: requestID)
    }

    var status: Int? {
        if case .server(let status, _, _, _, _) = self { return status }
        return nil
    }

    var code: APIErrorCode? {
        if case .server(_, let code, _, _, _) = self { return code }
        return nil
    }

    var isRetryable: Bool {
        switch self {
        case .server(_, _, _, let retryable, _): retryable
        case .network: true
        case .decoding, .invalidConfiguration: false
        }
    }

    var isNetwork: Bool {
        if case .network = self { return true }
        return false
    }
}

extension APIError: LocalizedError {
    var errorDescription: String? {
        switch self {
        case .server(let status, let code, let message, _, _):
            "\(message) (\(code.rawValue), HTTP \(status))"
        case .network(let message, let timedOut):
            timedOut ? "The server did not answer in time." : "Network problem: \(message)"
        case .decoding(let message):
            "Unexpected response from the server: \(message)"
        case .invalidConfiguration(let message):
            message
        }
    }
}
