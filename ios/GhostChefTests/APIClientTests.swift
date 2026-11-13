import Foundation
import Testing

@testable import GhostChef

/// Intercepts every request made through a session configured with it.
final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    struct Reply: Sendable {
        var status = 200
        var body = Data("{}".utf8)
        var error: URLError? = nil
    }

    final class Box: @unchecked Sendable {
        private let lock = NSLock()
        private var _reply = Reply()
        private var _requests: [(URLRequest, Data)] = []

        var reply: Reply {
            get { lock.withLock { _reply } }
            set { lock.withLock { _reply = newValue } }
        }
        var requests: [(URLRequest, Data)] { lock.withLock { _requests } }
        func record(_ r: URLRequest, _ body: Data) { lock.withLock { _requests.append((r, body)) } }
        func reset() { lock.withLock { _requests = []; _reply = Reply() } }
    }

    static let box = Box()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.box.record(request, Self.readBody(request))
        let reply = Self.box.reply
        if let error = reply.error {
            client?.urlProtocol(self, didFailWithError: error)
            return
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: reply.status, httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: reply.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    /// URLSession hands the body to protocols as a stream.
    static func readBody(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let n = stream.read(&buffer, maxLength: buffer.count)
            if n <= 0 { break }
            data.append(buffer, count: n)
        }
        return data
    }
}

final class ConfigBox: @unchecked Sendable {
    private let lock = NSLock()
    private var _config: APIConfig
    init(_ c: APIConfig) { _config = c }
    var config: APIConfig {
        get { lock.withLock { _config } }
        set { lock.withLock { _config = newValue } }
    }
}

@Suite("APIClient", .serialized)
struct APIClientTests {
    let configBox = ConfigBox(APIConfig(baseURL: URL(string: "http://192.168.1.20:8000"), demoKey: "secret-demo"))
    let client: APIClient

    init() {
        StubURLProtocol.box.reset()
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let box = configBox
        client = APIClient(session: URLSession(configuration: cfg)) { box.config }
    }

    var lastRequest: URLRequest? { StubURLProtocol.box.requests.last?.0 }
    var lastBody: Data { StubURLProtocol.box.requests.last?.1 ?? Data() }

    @Test func addsDemoKeyAndQuery() async throws {
        StubURLProtocol.box.reply.body = Data(#"{ "recipes": [] }"#.utf8)
        _ = try await client.recipes(status: .published)
        let r = try #require(lastRequest)
        #expect(r.value(forHTTPHeaderField: "X-Demo-Key") == "secret-demo")
        #expect(r.url?.absoluteString == "http://192.168.1.20:8000/recipes?status=published")
        #expect(r.httpMethod == "GET")
    }

    @Test func healthNeedsNoKey() async throws {
        StubURLProtocol.box.reply.body = Data(
            #"{ "status": "ok", "contract_version": "2.0", "ai_mode": "gemini", "storage": "supabase" }"#.utf8)
        let h = try await client.health()
        #expect(h.aiMode == "gemini")
        #expect(lastRequest?.value(forHTTPHeaderField: "X-Demo-Key") == nil)
    }

    @Test func settingsChangesApplyWithoutRestart() async throws {
        StubURLProtocol.box.reply.body = Data(#"{ "recipes": [] }"#.utf8)
        _ = try await client.recipes(status: nil)
        #expect(lastRequest?.url?.host() == "192.168.1.20")
        configBox.config = APIConfig(baseURL: URL(string: "https://ghostchef.up.railway.app"), demoKey: "k2")
        _ = try await client.recipes(status: nil)
        #expect(lastRequest?.url?.absoluteString == "https://ghostchef.up.railway.app/recipes")
        #expect(lastRequest?.value(forHTTPHeaderField: "X-Demo-Key") == "k2")
    }

    @Test func missingBaseURLIsAConfigurationError() async {
        configBox.config = APIConfig(baseURL: nil, demoKey: "")
        await #expect(throws: APIError.invalidConfiguration(
            message: "Set the backend URL in Settings (e.g. http://192.168.1.20:8000).")) {
            try await client.health()
        }
        #expect(StubURLProtocol.box.requests.isEmpty)
    }

    @Test func checkSendsMultipartFrame() async throws {
        StubURLProtocol.box.reply.body = Data(
            """
            { "request_id": "r1", "step_id": "s1", "verdict": "pass", "mistake_id": null, "headline": "Looks right",
              "fix": "", "spoken": "That looks right.", "confidence": 0.9, "latency_ms": 1200, "model": "m" }
            """.utf8)
        let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x01, 0x02, 0xFF, 0xD9])
        let captured = Date(timeIntervalSince1970: 1_794_648_600)
        let result = try await client.check(
            frame: jpeg, stepID: "s1", requestID: "r1", sessionID: "sess1", capturedAt: captured)
        #expect(result.verdict == .pass)

        let r = try #require(lastRequest)
        #expect(r.httpMethod == "POST")
        #expect(r.url?.path() == "/check")
        #expect(r.value(forHTTPHeaderField: "X-Demo-Key") == "secret-demo")
        let contentType = try #require(r.value(forHTTPHeaderField: "Content-Type"))
        #expect(contentType.hasPrefix("multipart/form-data; boundary="))
        let boundary = String(contentType.dropFirst("multipart/form-data; boundary=".count))

        let body = lastBody
        let text = String(decoding: body, as: UTF8.self)
        #expect(
            text.contains(
                "--\(boundary)\r\nContent-Disposition: form-data; name=\"frame\"; filename=\"frame.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
            ))
        #expect(body.range(of: jpeg) != nil, "JPEG bytes are in the body unchanged")
        #expect(text.contains("name=\"step_id\"\r\n\r\ns1\r\n"))
        #expect(text.contains("name=\"request_id\"\r\n\r\nr1\r\n"))
        #expect(text.contains("name=\"session_id\"\r\n\r\nsess1\r\n"))
        #expect(text.contains("name=\"captured_at\"\r\n\r\n2026-11-14T09:30:00.000Z\r\n"))
        #expect(text.hasSuffix("--\(boundary)--\r\n"))
    }

    @Test func watchOmitsOptionalFields() async throws {
        StubURLProtocol.box.reply.body = Data(
            """
            { "request_id": "r2", "step_id": "s1", "status": "ok", "mistake_id": null, "headline": "",
              "fix": "", "spoken": "", "confidence": 0.0, "latency_ms": 600, "model": "m" }
            """.utf8)
        _ = try await client.watch(frame: Data([1, 2, 3]), stepID: "s1", requestID: "r2", sessionID: nil, capturedAt: nil)
        let text = String(decoding: lastBody, as: UTF8.self)
        #expect(lastRequest?.url?.path() == "/watch")
        #expect(!text.contains("session_id"))
        #expect(!text.contains("captured_at"))
    }

    @Test func decodes429Envelope() async {
        StubURLProtocol.box.reply = .init(
            status: 429,
            body: Data(
                #"{ "error": { "code": "quota_exhausted", "message": "A watch call is already in flight", "retryable": true, "request_id": "r9" } }"#
                    .utf8))
        do {
            _ = try await client.watch(frame: Data([1]), stepID: "s", requestID: "r9", sessionID: nil, capturedAt: nil)
            Issue.record("expected an error")
        } catch let error as APIError {
            #expect(
                error == APIError(
                    status: 429, code: .quotaExhausted, message: "A watch call is already in flight",
                    retryable: true, requestID: "r9"))
            #expect(error.isRetryable)
        } catch {
            Issue.record("unexpected \(error)")
        }
    }

    @Test func decodes504Envelope() async {
        StubURLProtocol.box.reply = .init(
            status: 504,
            body: Data(
                #"{ "error": { "code": "model_timeout", "message": "Gemini did not answer within 8 s", "retryable": true, "request_id": null } }"#
                    .utf8))
        await #expect(
            throws: APIError(
                status: 504, code: .modelTimeout, message: "Gemini did not answer within 8 s", retryable: true)
        ) {
            try await client.check(frame: Data([1]), stepID: "s", requestID: "r", sessionID: nil, capturedAt: nil)
        }
    }

    @Test func nonEnvelopeErrorFallsBackToStatus() async {
        StubURLProtocol.box.reply = .init(status: 502, body: Data("Bad Gateway".utf8))
        do {
            _ = try await client.health()
            Issue.record("expected an error")
        } catch let error as APIError {
            #expect(error.status == 502)
            #expect(error.code == .internal)
            #expect(error.isRetryable)
        } catch {
            Issue.record("unexpected \(error)")
        }
    }

    @Test func transportFailuresMapToNetwork() async {
        StubURLProtocol.box.reply = .init(error: URLError(.notConnectedToInternet))
        await #expect(throws: APIError.self) { try await client.health() }
        do { _ = try await client.health() } catch let e as APIError {
            #expect(e.isNetwork)
            #expect(e == .network(message: URLError(.notConnectedToInternet).localizedDescription, timedOut: false))
        } catch { Issue.record("unexpected \(error)") }

        StubURLProtocol.box.reply = .init(error: URLError(.timedOut))
        do { _ = try await client.health() } catch let e as APIError {
            if case .network(_, let timedOut) = e { #expect(timedOut) } else { Issue.record("not network: \(e)") }
        } catch { Issue.record("unexpected \(error)") }
    }

    @Test func timeouts() async throws {
        let check = try client.makeFrameRequest(
            path: "check", frame: Data(), stepID: "s", requestID: "r", sessionID: nil, capturedAt: nil,
            timeout: APIClient.Timeout.check)
        #expect(check.timeoutInterval == 10)
        #expect(APIClient.Timeout.watch == 4)
        #expect(try client.makeRequest("GET", path: "recipes").timeoutInterval == 10)

        // And the values actually reach the wire.
        StubURLProtocol.box.reply.body = Data(
            """
            { "request_id": "r", "step_id": "s", "status": "ok", "mistake_id": null, "headline": "",
              "fix": "", "spoken": "", "confidence": 0.0, "latency_ms": 1, "model": "m" }
            """.utf8)
        _ = try await client.watch(frame: Data([1]), stepID: "s", requestID: "r", sessionID: nil, capturedAt: nil)
        #expect(lastRequest?.timeoutInterval == 4)
        StubURLProtocol.box.reply.body = Data(
            """
            { "request_id": "r", "step_id": "s", "verdict": "pass", "mistake_id": null, "headline": "",
              "fix": "", "spoken": "", "confidence": 0.9, "latency_ms": 1, "model": "m" }
            """.utf8)
        _ = try await client.check(frame: Data([1]), stepID: "s", requestID: "r", sessionID: nil, capturedAt: nil)
        #expect(lastRequest?.timeoutInterval == 10)
        StubURLProtocol.box.reply.body = Data(#"{ "recipes": [] }"#.utf8)
        _ = try await client.recipes(status: nil)
        #expect(lastRequest?.timeoutInterval == 10)
    }

    @Test func postEventSendsJSON() async throws {
        StubURLProtocol.box.reply = .init(status: 201, body: Data(#"{ "event_id": "e1" }"#.utf8))
        let created = try await client.postEvent(
            sessionID: "sess1", kind: .stepChange, stepID: "s2", requestID: nil,
            payload: ["from_idx": 1, "to_idx": 2, "via": "tap"])
        #expect(created.eventID == "e1")
        let r = try #require(lastRequest)
        #expect(r.url?.path() == "/sessions/sess1/events")
        #expect(r.value(forHTTPHeaderField: "Content-Type") == "application/json; charset=utf-8")
        let json = try #require(try JSONSerialization.jsonObject(with: lastBody) as? [String: Any])
        #expect(json["kind"] as? String == "step_change")
        #expect(json["step_id"] as? String == "s2")
        #expect((json["payload"] as? [String: Any])?["to_idx"] as? Int == 2)
    }

    @Test func liveTokenQuery() async throws {
        StubURLProtocol.box.reply = .init(status: 503, body: Data())
        _ = try? await client.liveToken(recipeID: "rec", sessionID: "sess")
        #expect(lastRequest?.url?.absoluteString == "http://192.168.1.20:8000/live-token?recipe_id=rec&session_id=sess")
    }
}
