import Foundation
import Observation

// IOS-08.4: a finished take → `POST /recipes` → video straight to Storage → `/process`.
// TUS shapes follow Supabase "Resumable uploads" (presigned: `x-signature` instead of a bearer
// token) and API-CONTRACT §2: chunk size exactly 6 MB, metadata bucketName / objectName /
// contentType. The demo key is never sent to Storage.

/// HTTP for uploads, injected so the TUS / PUT logic runs in tests without a network.
protocol UploadTransport: Sendable {
    func send(_ request: URLRequest, body: Data?) async throws -> (HTTPURLResponse, Data)
    /// Streams a file as the request body, reporting bytes sent.
    func upload(
        _ request: URLRequest, fromFile url: URL, progress: @escaping @Sendable (Int64) -> Void
    ) async throws -> (HTTPURLResponse, Data)
}

enum UploadError: Error, Equatable, LocalizedError {
    case http(status: Int, body: String)
    case missingLocation
    case notHTTP
    case fileMissing

    var errorDescription: String? {
        switch self {
        case .http(let status, let body): "Upload failed (\(status)) \(body.prefix(120))"
        case .missingLocation: "The upload server did not say where to send the video"
        case .notHTTP: "Not an HTTP response"
        case .fileMissing: "The recording is no longer on the phone"
        }
    }
}

@MainActor
@Observable
final class ChefUploader {
    enum Method: String, Equatable, Sendable {
        case tus = "Resumable upload"
        case put = "Single upload"
    }

    enum Phase: Equatable {
        case idle
        case creating
        case uploading(Method, sent: Int64, total: Int64)
        case retrying(String, inSeconds: Int)
        case processing
        case done(recipeID: String, title: String, reviewURL: URL?)
        case failed(String)
    }

    static let chunkSize = 6 * 1024 * 1024
    /// Delay before each try (IOS-08.4): 0, 3, 5, 10, 20 s.
    static let backoff: [Duration] = [.zero, .seconds(3), .seconds(5), .seconds(10), .seconds(20)]
    /// Whole TUS runs before falling back to a single PUT.
    static let tusRunsBeforeFallback = 2

    private(set) var phase: Phase = .idle
    /// Which way the last upload went, for STATUS.md ("TUS / PUT").
    private(set) var methodUsed: Method?

    @ObservationIgnored private let api: any GhostChefAPI
    @ObservationIgnored private let transport: any UploadTransport
    @ObservationIgnored private let store: TakeStore
    @ObservationIgnored private let clock: any CookClock
    @ObservationIgnored private let reviewURL: @MainActor () -> URL?
    /// The TUS upload URL per take, so a retry resumes instead of creating a new upload.
    @ObservationIgnored private var tusLocations: [String: URL] = [:]

    init(
        api: any GhostChefAPI, transport: any UploadTransport, store: TakeStore,
        clock: any CookClock = SystemCookClock(), reviewURL: @escaping @MainActor () -> URL? = { nil }
    ) {
        self.api = api
        self.transport = transport
        self.store = store
        self.clock = clock
        self.reviewURL = reviewURL
    }

    var isBusy: Bool {
        switch phase {
        case .creating, .uploading, .retrying, .processing: true
        default: false
        }
    }

    // MARK: Run

    /// Runs the whole flow for one take. Safe to call again after a failure: a recipe already
    /// created is reused while its upload URL is valid.
    func upload(_ take: TakeRecord) async {
        var record = take
        let file = store.videoURL(for: record.id)
        guard FileManager.default.fileExists(atPath: file.path) else {
            phase = .failed(UploadError.fileMissing.localizedDescription)
            return
        }
        do {
            // 1. The recipe (once).
            if record.upload == nil || record.upload!.uploadExpiresAt <= clock.now {
                phase = .creating
                record.upload = try await api.createRecipe(
                    title: record.title, chefName: record.chefName, stepMarksS: record.stepMarksS,
                    consent: record.consent)
                tusLocations[record.id] = nil
                try? store.save(record)
            }
            guard let upload = record.upload else { return }

            // 2. The video.
            try await sendVideo(take: record.id, file: file, upload: upload)

            // 3. Processing; one more upload if the server did not see the file.
            phase = .processing
            do {
                try await api.processRecipe(id: upload.recipeID)
            } catch let error as APIError where error.code == .uploadMissing {
                tusLocations[record.id] = nil
                try await sendVideo(take: record.id, file: file, upload: upload)
                phase = .processing
                try await api.processRecipe(id: upload.recipeID)
            }

            // 4. Only now does the MP4 leave the phone.
            record.processedAt = clock.now
            store.delete(record.id)
            tusLocations[record.id] = nil
            phase = .done(recipeID: upload.recipeID, title: record.title, reviewURL: reviewURL())
        } catch is CancellationError {
            phase = .failed("Upload cancelled. The take is still on the phone.")
        } catch {
            try? store.save(record)
            phase = .failed("\(error.localizedDescription). The take is still on the phone; try again.")
        }
    }

    private func sendVideo(take id: String, file: URL, upload: RecipeUpload) async throws {
        let size = try Self.fileSize(file)
        if let endpoint = upload.resumableEndpoint {
            for run in 1...Self.tusRunsBeforeFallback {
                do {
                    try await tusUpload(take: id, file: file, size: size, endpoint: endpoint, upload: upload)
                    methodUsed = .tus
                    return
                } catch is CancellationError {
                    throw CancellationError()
                } catch {
                    log("TUS run \(run) failed: \(error.localizedDescription)")
                }
            }
            log("TUS failed twice: falling back to a single PUT")
        }
        try await putUpload(file: file, size: size, upload: upload)
        methodUsed = .put
    }

    // MARK: TUS

    private func tusUpload(take id: String, file: URL, size: Int64, endpoint: URL, upload: RecipeUpload) async throws {
        phase = .uploading(.tus, sent: 0, total: size)
        let location: URL
        if let known = tusLocations[id] {
            location = known
        } else {
            location = try await withRetries("Starting upload") {
                try await self.tusCreate(endpoint: endpoint, size: size, upload: upload)
            }
            tusLocations[id] = location
        }
        var offset = try await withRetries("Resuming upload") {
            try await self.tusOffset(location: location, upload: upload)
        }
        phase = .uploading(.tus, sent: offset, total: size)
        while offset < size {
            let length = Int(min(Int64(Self.chunkSize), size - offset))
            let chunk = try Self.read(file, offset: offset, length: length)
            let sentFrom = offset
            offset = try await withRetries("Uploading") { attempt in
                // After a failure the server may hold part of the chunk: ask where it stands.
                if attempt > 0 {
                    let server = try await self.tusOffset(location: location, upload: upload)
                    if server != sentFrom { return server }
                }
                return try await self.tusPatch(location: location, offset: sentFrom, chunk: chunk, upload: upload)
            }
            phase = .uploading(.tus, sent: offset, total: size)
        }
    }

    private func tusCreate(endpoint: URL, size: Int64, upload: RecipeUpload) async throws -> URL {
        var request = Self.tusRequest("POST", url: endpoint, upload: upload)
        request.setValue(String(size), forHTTPHeaderField: "Upload-Length")
        request.setValue(Self.tusMetadata(upload), forHTTPHeaderField: "Upload-Metadata")
        request.setValue("true", forHTTPHeaderField: "x-upsert")
        let (response, data) = try await transport.send(request, body: nil)
        try Self.expect(response, data, [200, 201])
        guard let raw = response.value(forHTTPHeaderField: "Location"),
            let location = URL(string: raw, relativeTo: endpoint)?.absoluteURL
        else { throw UploadError.missingLocation }
        return location
    }

    private func tusOffset(location: URL, upload: RecipeUpload) async throws -> Int64 {
        var request = Self.tusRequest("HEAD", url: location, upload: upload)
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        let (response, data) = try await transport.send(request, body: nil)
        try Self.expect(response, data, [200, 204])
        return Int64(response.value(forHTTPHeaderField: "Upload-Offset") ?? "") ?? 0
    }

    private func tusPatch(location: URL, offset: Int64, chunk: Data, upload: RecipeUpload) async throws -> Int64 {
        var request = Self.tusRequest("PATCH", url: location, upload: upload)
        request.setValue(String(offset), forHTTPHeaderField: "Upload-Offset")
        request.setValue("application/offset+octet-stream", forHTTPHeaderField: "Content-Type")
        let (response, data) = try await transport.send(request, body: chunk)
        try Self.expect(response, data, [200, 204])
        return Int64(response.value(forHTTPHeaderField: "Upload-Offset") ?? "") ?? offset + Int64(chunk.count)
    }

    static func tusRequest(_ method: String, url: URL, upload: RecipeUpload) -> URLRequest {
        var request = URLRequest(url: url, timeoutInterval: 60)
        request.httpMethod = method
        request.setValue("1.0.0", forHTTPHeaderField: "Tus-Resumable")
        request.setValue(upload.uploadToken, forHTTPHeaderField: "x-signature")
        return request
    }

    /// `key base64(value)` pairs, comma-separated (TUS creation extension).
    static func tusMetadata(_ upload: RecipeUpload) -> String {
        [("bucketName", upload.bucket), ("objectName", upload.objectPath), ("contentType", "video/mp4"), ("cacheControl", "3600")]
            .map { "\($0.0) \(Data($0.1.utf8).base64EncodedString())" }
            .joined(separator: ",")
    }

    // MARK: PUT

    private func putUpload(file: URL, size: Int64, upload: RecipeUpload) async throws {
        phase = .uploading(.put, sent: 0, total: size)
        try await withRetries("Uploading") {
            var request = URLRequest(url: upload.uploadURL, timeoutInterval: 600)
            request.httpMethod = "PUT"
            request.setValue("video/mp4", forHTTPHeaderField: "Content-Type")
            // Storage URL: no X-Demo-Key (API-CONTRACT §2).
            let (response, data) = try await self.transport.upload(request, fromFile: file) { sent in
                Task { @MainActor [weak self] in
                    guard let self, case .uploading(.put, _, let total) = self.phase else { return }
                    self.phase = .uploading(.put, sent: min(sent, total), total: total)
                }
            }
            try Self.expect(response, data, Array(200..<300))
            self.phase = .uploading(.put, sent: size, total: size)
        }
    }

    // MARK: Helpers

    @discardableResult
    private func withRetries<T>(_ what: String, _ operation: @escaping @MainActor () async throws -> T) async throws -> T {
        try await withRetries(what) { _ in try await operation() }
    }

    /// Tries with the IOS-08.4 back-off; gives up at once on errors a retry cannot fix.
    @discardableResult
    private func withRetries<T>(_ what: String, _ operation: @escaping @MainActor (Int) async throws -> T) async throws -> T {
        var lastError: (any Error)?
        let resume = phase
        for (attempt, delay) in Self.backoff.enumerated() {
            if delay > .zero {
                phase = .retrying(what, inSeconds: Int(delay.timeInterval))
                try await clock.sleep(for: delay)
                phase = resume
            }
            do {
                return try await operation(attempt)
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                lastError = error
                log("\(what) failed (try \(attempt + 1)): \(error.localizedDescription)")
                guard Self.isRetryable(error) else { throw error }
            }
        }
        throw lastError ?? UploadError.notHTTP
    }

    /// Network errors, timeouts, 408 / 409 (TUS offset race) / 423 / 429 and 5xx are retried;
    /// other 4xx (expired or bad token, too large) are not.
    static func isRetryable(_ error: any Error) -> Bool {
        if case UploadError.http(let status, _) = error {
            return status >= 500 || [408, 409, 423, 429].contains(status)
        }
        if error is UploadError { return false }
        return true
    }

    private static func expect(_ response: HTTPURLResponse, _ data: Data, _ ok: [Int]) throws {
        guard ok.contains(response.statusCode) else {
            throw UploadError.http(status: response.statusCode, body: String(decoding: data.prefix(200), as: UTF8.self))
        }
    }

    static func fileSize(_ url: URL) throws -> Int64 {
        guard let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber else {
            throw UploadError.fileMissing
        }
        return size.int64Value
    }

    static func read(_ url: URL, offset: Int64, length: Int) throws -> Data {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(offset))
        return try handle.read(upToCount: length) ?? Data()
    }

    private func log(_ text: String) {
        print("[chef upload] \(text)")
    }
}

/// `URLSession` implementation. The PUT streams the file from disk (no 500 MB in memory).
struct URLSessionUploadTransport: UploadTransport {
    let session: URLSession

    init(session: URLSession = .shared) {
        self.session = session
    }

    func send(_ request: URLRequest, body: Data?) async throws -> (HTTPURLResponse, Data) {
        let (data, response) =
            if let body {
                try await session.upload(for: request, from: body)
            } else {
                try await session.data(for: request)
            }
        guard let http = response as? HTTPURLResponse else { throw UploadError.notHTTP }
        return (http, data)
    }

    func upload(
        _ request: URLRequest, fromFile url: URL, progress: @escaping @Sendable (Int64) -> Void
    ) async throws -> (HTTPURLResponse, Data) {
        let delegate = UploadProgressDelegate(progress: progress)
        let (data, response) = try await session.upload(for: request, fromFile: url, delegate: delegate)
        guard let http = response as? HTTPURLResponse else { throw UploadError.notHTTP }
        return (http, data)
    }
}

private final class UploadProgressDelegate: NSObject, URLSessionTaskDelegate, Sendable {
    let progress: @Sendable (Int64) -> Void

    init(progress: @escaping @Sendable (Int64) -> Void) {
        self.progress = progress
    }

    func urlSession(
        _ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64,
        totalBytesExpectedToSend: Int64
    ) {
        progress(totalBytesSent)
    }
}
