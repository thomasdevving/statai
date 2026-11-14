import Foundation

// The Live WebSocket (IOS-05.1). The phone talks to Gemini directly with the ephemeral token from
// `GET /live-token`; the real API key never reaches the phone.

enum LiveClientError: Error, Equatable, LocalizedError {
    /// The server closed the socket before `setupComplete` (e.g. 1011 "Token has been used too
    /// many times").
    case closedBeforeSetup(code: Int, reason: String)
    case setupTimedOut
    case closed

    var errorDescription: String? {
        switch self {
        case .closedBeforeSetup(let code, let reason): "Live closed before setup (\(code)) \(reason)"
        case .setupTimedOut: "Live did not answer the setup in time"
        case .closed: "Live connection closed"
        }
    }
}

/// An open, set-up Live session.
protocol LiveConnection: AnyObject, Sendable {
    /// Decoded server events in order. Finishes when the socket closes for any reason.
    var events: AsyncStream<LiveServerEvent> { get }
    func send(_ message: Data) async throws
    func close()
}

/// Opens Live sessions. Injected so `VoiceController` runs in tests without a network.
protocol LiveConnecting: Sendable {
    /// Opens the socket, sends the setup message, and returns only after `setupComplete`.
    func connect(token: LiveTokenResponse, resumeHandle: String?) async throws -> any LiveConnection
}

struct LiveClient: LiveConnecting {
    /// `setupComplete` came 1.1–1.7 s after connect in the AI-05 run; 10 s allows bad venue Wi-Fi.
    static let setupTimeout: Duration = .seconds(10)

    let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func connect(token: LiveTokenResponse, resumeHandle: String?) async throws -> any LiveConnection {
        let task = session.webSocketTask(with: LiveEndpoint.request(token: token.token))
        let connection = WebSocketLiveConnection(task: task)
        do {
            try await connection.open(setup: LiveOutgoing.setup(token: token, resumeHandle: resumeHandle))
        } catch {
            connection.close()
            throw error
        }
        return connection
    }
}

final class WebSocketLiveConnection: LiveConnection, @unchecked Sendable {
    let events: AsyncStream<LiveServerEvent>
    private let continuation: AsyncStream<LiveServerEvent>.Continuation
    private let task: URLSessionWebSocketTask
    private let lock = NSLock()
    private var receiveLoop: Task<Void, Never>?
    private var isClosed = false

    init(task: URLSessionWebSocketTask) {
        self.task = task
        (events, continuation) = AsyncStream.makeStream(of: LiveServerEvent.self, bufferingPolicy: .unbounded)
    }

    /// Sends the setup and waits for `setupComplete`; nothing else may be sent before it.
    func open(setup: Data) async throws {
        task.resume()
        try await send(setup)
        let task = task
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask {
                while true {
                    let message: URLSessionWebSocketTask.Message
                    do {
                        message = try await task.receive()
                    } catch {
                        throw LiveClientError.closedBeforeSetup(
                            code: task.closeCode.rawValue,
                            reason: task.closeReason.map { String(decoding: $0, as: UTF8.self) } ?? "")
                    }
                    if Self.decode(message).contains(.setupComplete) { return }
                }
            }
            group.addTask {
                try await Task.sleep(for: LiveClient.setupTimeout)
                throw LiveClientError.setupTimedOut
            }
            defer { group.cancelAll() }
            try await group.next()
        }
        startReceiving()
    }

    func send(_ message: Data) async throws {
        guard !lock.withLock({ isClosed }) else { throw LiveClientError.closed }
        // JSON text frames, as the AI-05 smoke script sent them.
        try await task.send(.string(String(decoding: message, as: UTF8.self)))
    }

    func close() {
        let wasOpen = lock.withLock {
            defer { isClosed = true }
            return !isClosed
        }
        guard wasOpen else { return }
        receiveLoop?.cancel()
        task.cancel(with: .normalClosure, reason: nil)
        continuation.finish()
    }

    private func startReceiving() {
        let task = task
        let continuation = continuation
        receiveLoop = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    let message = try await task.receive()
                    for event in Self.decode(message) { continuation.yield(event) }
                } catch {
                    break
                }
            }
            self?.lock.withLock { self?.isClosed = true }
            continuation.finish()
        }
    }

    /// Server frames are binary JSON; text frames are handled the same way.
    private static func decode(_ message: URLSessionWebSocketTask.Message) -> [LiveServerEvent] {
        switch message {
        case .data(let data): LiveIncoming.decode(data)
        case .string(let text): LiveIncoming.decode(Data(text.utf8))
        @unknown default: []
        }
    }
}
