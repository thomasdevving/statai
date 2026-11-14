@preconcurrency import AVFoundation
import Foundation
import Testing

@testable import GhostChef

// IOS-08: Chef mode. Contract shapes, step marks, the recorder state machine, the take store,
// the uploader (TUS / PUT / process) against a fake server, and the MP4 writer for real.

// MARK: - Contract (08.2)

@Suite("Chef contract")
struct ChefContractTests {
    static let created = """
        {
          "recipe_id": "6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60",
          "status": "uploading",
          "upload_url": "https://abc.supabase.co/storage/v1/object/upload/sign/videos/6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60/source.mp4?token=xyz",
          "upload_token": "xyz",
          "bucket": "videos",
          "object_path": "6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60/source.mp4",
          "resumable_endpoint": "https://abc.storage.supabase.co/storage/v1/upload/resumable",
          "upload_expires_at": "2026-11-14T11:30:00Z"
        }
        """

    @Test func decodesThe201WithAResumableEndpoint() throws {
        let u = try JSONCoding.decoder.decode(RecipeUpload.self, from: Data(Self.created.utf8))
        #expect(u.recipeID == "6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60")
        #expect(u.status == .uploading)
        #expect(u.uploadURL.absoluteString.hasSuffix("source.mp4?token=xyz"))
        #expect(u.uploadToken == "xyz" && u.bucket == "videos")
        #expect(u.objectPath == "6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60/source.mp4")
        #expect(u.resumableEndpoint?.absoluteString == "https://abc.storage.supabase.co/storage/v1/upload/resumable")
        #expect(u.uploadExpiresAt == ISO8601.date(from: "2026-11-14T11:30:00Z"))
    }

    @Test func decodesThe201InMemoryModeWithoutAResumableEndpoint() throws {
        let memory = Self.created.replacingOccurrences(
            of: "\"https://abc.storage.supabase.co/storage/v1/upload/resumable\"", with: "null")
        #expect(try JSONCoding.decoder.decode(RecipeUpload.self, from: Data(memory.utf8)).resumableEndpoint == nil)
        let absent = Self.created.replacingOccurrences(
            of: "\"resumable_endpoint\": \"https://abc.storage.supabase.co/storage/v1/upload/resumable\",", with: "")
        #expect(try JSONCoding.decoder.decode(RecipeUpload.self, from: Data(absent.utf8)).resumableEndpoint == nil)
    }

    @Test func uploadMissingEnvelope() {
        let body = #"{ "error": { "code": "upload_missing", "message": "no video at the upload path", "retryable": false, "request_id": null } }"#
        let error = APIClient.decodeError(status: 409, data: Data(body.utf8))
        #expect(error.status == 409 && error.code == .uploadMissing)
    }

    @Test func createBodyIsSnakeCase() throws {
        let body = RecipeCreate(title: "Ham and cheese sandwich", chefName: nil, stepMarksS: [12.4, 58.0], consent: true)
        let json = try #require(try JSONSerialization.jsonObject(with: JSONCoding.encoder.encode(body)) as? [String: Any])
        #expect(json["title"] as? String == "Ham and cheese sandwich")
        #expect(json["step_marks_s"] as? [Double] == [12.4, 58.0])
        #expect(json["consent"] as? Bool == true)
        #expect(json["chef_name"] == nil)
    }

    @Test func processStartedDecodes() throws {
        let p = try JSONCoding.decoder.decode(ProcessStarted.self, from: Data(#"{ "recipe_id": "r1", "status": "processing" }"#.utf8))
        #expect(p == ProcessStarted(recipeID: "r1", status: .processing))
    }
}

// MARK: - Step marks (08.3)

@Suite("Step marks")
struct StepMarkTests {
    let t0 = Date(timeIntervalSince1970: 1_800_000_000)

    @Test func marksAreRelativeAscendingAndCollapseWithinOneSecond() {
        var m = StepMarkCollector()
        #expect(m.mark(at: t0) == nil, "not recording yet")
        m.start(at: t0)
        #expect(m.currentStep == 1)
        #expect(m.mark(at: t0.addingTimeInterval(12.404)) == 2)
        #expect(m.mark(at: t0.addingTimeInterval(12.9)) == nil, "within 1 s of the last mark")
        #expect(m.mark(at: t0.addingTimeInterval(58)) == 3)
        #expect(m.mark(at: t0.addingTimeInterval(-1)) == nil)
        #expect(m.marks == [12.4, 58.0])
        #expect(m.currentStep == 3)
    }

    @Test func resetBetweenTakes() {
        var m = StepMarkCollector()
        m.start(at: t0)
        m.mark(at: t0.addingTimeInterval(5))
        m.reset()
        #expect(m.marks.isEmpty && m.startedAt == nil)
        m.start(at: t0.addingTimeInterval(100))
        #expect(m.mark(at: t0.addingTimeInterval(103)) == 2)
        #expect(m.marks == [3.0])
    }

    @Test func clockFormat() {
        #expect(recordingClock(0) == "00:00")
        #expect(recordingClock(192.9) == "03:12")
        #expect(recordingClock(-3) == "00:00")
    }
}

// MARK: - Recorder (08.3)

@MainActor
final class FakeTakeCapture: TakeCapturing {
    var source: TakeSource = .phone
    var started: URL?
    var startError: (any Error)?
    var result = TakeCaptureResult(durationS: 30, width: 720, height: 1280, videoFrames: 720, hasAudio: true)

    func start(writingTo url: URL) async throws {
        if let startError { throw startError }
        started = url
        try Data("mp4".utf8).write(to: url)
    }

    func stop() async throws -> TakeCaptureResult { result }
}

@MainActor
final class FakeChefLens: ChefLens {
    var shown: [(elapsed: TimeInterval, step: Int, marked: Bool)] = []
    var clears = 0
    func showRecording(elapsed: TimeInterval, step: Int, justMarked: Bool) { shown.append((elapsed, step, justMarked)) }
    func clear() { clears += 1 }
}

@MainActor
final class FakeChefFeedback: ChefFeedback {
    var clicks = 0
    func markClick() { clicks += 1 }
}

private func tempStore() -> TakeStore {
    TakeStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("ChefTests-\(UUID().uuidString)"))
}

@MainActor
@Suite("Chef recorder")
struct ChefRecorderTests {
    let capture = FakeTakeCapture()
    let lens = FakeChefLens()
    let feedback = FakeChefFeedback()
    let clock = TestClock()
    let store = tempStore()
    let recorder: ChefRecorder

    init() {
        recorder = ChefRecorder(capture: capture, store: store, clock: clock)
        recorder.attach(lens: lens, feedback: feedback)
    }

    @Test func cannotRecordWithoutConsent() async {
        await recorder.start()
        #expect(capture.started == nil)
        if case .failed = recorder.phase {} else { Issue.record("expected failed, got \(recorder.phase)") }
        #expect(!recorder.canStart)
    }

    @Test func recordsMarksShowsTheLensAndSavesTheTake() async throws {
        recorder.consentGiven = true
        #expect(recorder.canStart)
        await recorder.start()
        #expect(recorder.phase == .recording)
        #expect(lens.shown.last?.step == 1)

        await eventually("ticker waiting") { clock.pendingCount == 1 }
        clock.advance(by: .seconds(1))
        await eventually("tick") { lens.shown.count == 2 }
        #expect(lens.shown.last?.elapsed == 1)

        await eventually("ticker waiting again") { clock.pendingCount == 1 }
        clock.advance(by: .milliseconds(400))  // 1.4 s, before the next tick
        recorder.mark()
        recorder.mark()  // same instant: collapsed
        #expect(feedback.clicks == 1)
        #expect(recorder.marks.marks == [1.4])
        clock.advance(by: .milliseconds(600))  // 2.0 s: the tick shows it
        await eventually("marked shown") { lens.shown.last?.marked == true }
        #expect(lens.shown.last?.step == 2)

        capture.result.durationS = 1.0  // the 1.4 s mark falls after the written end
        await recorder.stop()
        guard case .naming(let record) = recorder.phase else {
            Issue.record("expected naming, got \(recorder.phase)")
            return
        }
        #expect(record.stepMarksS.isEmpty, "a mark after the end of the file is dropped")
        #expect(record.consent && record.source == .phone && record.durationS == 1.0)
        #expect(lens.clears == 1)
        #expect(FileManager.default.fileExists(atPath: store.videoURL(for: record.id).path))
    }

    @Test func titleIsRequiredAndCappedThenTheTakeIsPending() async throws {
        recorder.consentGiven = true
        await recorder.start()
        clock.advance(by: .seconds(5))
        recorder.mark()
        await recorder.stop()
        #expect(recorder.finish(title: "   ", chefName: "") == nil)
        #expect(recorder.titleError != nil)
        #expect(recorder.finish(title: String(repeating: "a", count: 81), chefName: "") == nil)
        let saved = try #require(recorder.finish(title: " Ham and cheese ", chefName: " Aiko "))
        #expect(saved.title == "Ham and cheese" && saved.chefName == "Aiko")
        #expect(saved.stepMarksS == [5.0])
        #expect(recorder.phase == .idle)
        #expect(!recorder.consentGiven, "consent is asked again for the next take")
        #expect(store.pending().map(\.id) == [saved.id])
    }

    @Test func discardDeletesTheTake() async throws {
        recorder.consentGiven = true
        await recorder.start()
        await recorder.stop()
        guard case .naming(let record) = recorder.phase else { return }
        recorder.discard()
        #expect(!FileManager.default.fileExists(atPath: store.videoURL(for: record.id).path))
        #expect(store.pending().isEmpty)
    }

    @Test func aCaptureThatCannotStartFails() async {
        recorder.consentGiven = true
        capture.startError = TakeWriter.WriterError.noVideo
        await recorder.start()
        if case .failed = recorder.phase {} else { Issue.record("expected failed") }
        #expect(recorder.canStart, "can try again")
    }
}

// MARK: - Uploader (08.4)

/// A clock whose sleeps return at once and are recorded.
final class ImmediateClock: CookClock, @unchecked Sendable {
    private let lock = NSLock()
    private var t = Date()
    private var _sleeps: [Duration] = []
    var sleeps: [Duration] { lock.withLock { _sleeps } }
    var now: Date { lock.withLock { t } }
    func sleep(for duration: Duration) async throws {
        lock.withLock {
            _sleeps.append(duration)
            t = t.addingTimeInterval(duration.timeInterval)
        }
    }
}

/// Plays a scripted Storage server and records every request.
final class FakeUploadServer: UploadTransport, @unchecked Sendable {
    struct Seen: Sendable {
        let method: String
        let url: URL
        let headers: [String: String]
        let bodyBytes: Int
    }

    private let lock = NSLock()
    private var _seen: [Seen] = []
    /// TUS state: bytes the server holds.
    private var held: Int64 = 0
    var location = URL(string: "https://abc.storage.supabase.co/storage/v1/upload/resumable/upload-1")!
    /// Failures to inject, matched by method, consumed in order.
    var failures: [(method: String, error: any Error)] = []
    var putStatus = 200

    var seen: [Seen] { lock.withLock { _seen } }

    private func record(_ request: URLRequest, bytes: Int) -> (any Error)? {
        lock.withLock {
            _seen.append(Seen(method: request.httpMethod ?? "", url: request.url!, headers: request.allHTTPHeaderFields ?? [:], bodyBytes: bytes))
            if let i = failures.firstIndex(where: { $0.method == request.httpMethod }) {
                return failures.remove(at: i).error
            }
            return nil
        }
    }

    private func response(_ request: URLRequest, _ status: Int, _ headers: [String: String] = [:]) -> HTTPURLResponse {
        HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: headers)!
    }

    func send(_ request: URLRequest, body: Data?) async throws -> (HTTPURLResponse, Data) {
        if let error = record(request, bytes: body?.count ?? 0) { throw error }
        switch request.httpMethod {
        case "POST":
            return (response(request, 201, ["Location": location.absoluteString]), Data())
        case "HEAD":
            return (response(request, 200, ["Upload-Offset": String(lock.withLock { held })]), Data())
        case "PATCH":
            let offset = Int64(request.value(forHTTPHeaderField: "Upload-Offset") ?? "") ?? -1
            let current = lock.withLock { held }
            guard offset == current else { return (response(request, 409), Data("offset".utf8)) }
            let new = lock.withLock {
                held += Int64(body?.count ?? 0)
                return held
            }
            return (response(request, 204, ["Upload-Offset": String(new)]), Data())
        default:
            return (response(request, 405), Data())
        }
    }

    func upload(_ request: URLRequest, fromFile url: URL, progress: @escaping @Sendable (Int64) -> Void) async throws -> (HTTPURLResponse, Data) {
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.intValue ?? 0
        if let error = record(request, bytes: size) { throw error }
        progress(Int64(size))
        return (response(request, putStatus), Data())
    }
}

@MainActor
@Suite("Chef uploader")
struct ChefUploaderTests {
    let api: MockAPI
    let server = FakeUploadServer()
    let clock = ImmediateClock()
    let store = tempStore()
    let uploader: ChefUploader

    init() throws {
        api = MockAPI(recipe: try FixtureRecipe.load())
        uploader = ChefUploader(
            api: api, transport: server, store: store, clock: clock,
            reviewURL: { URL(string: "http://laptop:8000/app/review/") })
    }

    /// A saved, titled take with a file of `bytes` bytes.
    private func take(bytes: Int, upload: RecipeUpload? = nil) throws -> TakeRecord {
        try store.prepare()
        let id = store.newTakeID()
        try Data(count: bytes).write(to: store.videoURL(for: id))
        var record = TakeRecord(
            id: id, source: .glasses, recordedAt: clock.now, durationS: 60, stepMarksS: [12.4, 58], consent: true)
        record.title = "Ham and cheese sandwich"
        record.upload = upload
        try store.save(record)
        return record
    }

    private func resumable(_ id: String = "r1") -> RecipeUpload {
        RecipeUpload(
            recipeID: id, status: .uploading,
            uploadURL: URL(string: "https://abc.supabase.co/storage/v1/object/upload/sign/videos/\(id)/source.mp4?token=xyz")!,
            uploadToken: "xyz", bucket: "videos", objectPath: "\(id)/source.mp4",
            resumableEndpoint: URL(string: "https://abc.storage.supabase.co/storage/v1/upload/resumable")!,
            uploadExpiresAt: clock.now.addingTimeInterval(7200))
    }

    @Test func memoryModeUsesOnePutWithoutTheDemoKeyThenProcessesAndDeletesTheFile() async throws {
        let record = try take(bytes: 1000)
        await uploader.upload(record)
        guard case .done(let recipeID, let title, let review) = uploader.phase else {
            Issue.record("expected done, got \(uploader.phase)")
            return
        }
        #expect(title == "Ham and cheese sandwich")
        #expect(review?.absoluteString == "http://laptop:8000/app/review/")
        #expect(uploader.methodUsed == .put)
        let put = try #require(server.seen.first)
        #expect(put.method == "PUT" && put.bodyBytes == 1000)
        #expect(put.headers["Content-Type"] == "video/mp4")
        #expect(put.headers[APIClient.demoKeyHeader] == nil, "Storage never gets the demo key")
        let calls = await api.calls
        #expect(calls.contains(.createRecipe(title: "Ham and cheese sandwich", marks: [12.4, 58])))
        #expect(calls.contains(.processRecipe(recipeID)))
        #expect(!FileManager.default.fileExists(atPath: store.videoURL(for: record.id).path))
        #expect(store.pending().isEmpty)
    }

    @Test func tusUploadsInExactSixMegabyteChunks() async throws {
        let size = 13 * 1024 * 1024
        let record = try take(bytes: size, upload: resumable())
        await uploader.upload(record)
        #expect(uploader.methodUsed == .tus)
        let seen = server.seen
        #expect(seen.map(\.method) == ["POST", "HEAD", "PATCH", "PATCH", "PATCH"])
        let create = seen[0]
        #expect(create.url.absoluteString == "https://abc.storage.supabase.co/storage/v1/upload/resumable")
        #expect(create.headers["Tus-Resumable"] == "1.0.0")
        #expect(create.headers["x-signature"] == "xyz")
        #expect(create.headers["Upload-Length"] == String(size))
        #expect(create.headers[APIClient.demoKeyHeader] == nil)
        let metadata = create.headers["Upload-Metadata"] ?? ""
        let pairs = Dictionary(uniqueKeysWithValues: metadata.split(separator: ",").map { pair -> (String, String) in
            let parts = pair.split(separator: " ")
            return (String(parts[0]), String(decoding: Data(base64Encoded: String(parts[1])) ?? Data(), as: UTF8.self))
        })
        #expect(pairs["bucketName"] == "videos")
        #expect(pairs["objectName"] == "r1/source.mp4")
        #expect(pairs["contentType"] == "video/mp4")
        let patches = seen.filter { $0.method == "PATCH" }
        #expect(patches.map(\.bodyBytes) == [6 * 1024 * 1024, 6 * 1024 * 1024, 1024 * 1024])
        #expect(patches.map { $0.headers["Upload-Offset"] } == ["0", String(6 * 1024 * 1024), String(12 * 1024 * 1024)])
        #expect(patches.allSatisfy { $0.headers["Content-Type"] == "application/offset+octet-stream" && $0.url == server.location })
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
    }

    @Test func aDroppedChunkResumesFromTheServersOffset() async throws {
        let size = 7 * 1024 * 1024
        let record = try take(bytes: size, upload: resumable())
        server.failures = [("PATCH", URLError(.networkConnectionLost))]
        await uploader.upload(record)
        #expect(uploader.methodUsed == .tus)
        #expect(server.seen.map(\.method) == ["POST", "HEAD", "PATCH", "HEAD", "PATCH", "PATCH"])
        #expect(clock.sleeps == [.seconds(3)], "backed off once")
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
    }

    @Test func tusFailingTwiceFallsBackToPut() async throws {
        let record = try take(bytes: 2048, upload: resumable())
        server.failures = [
            ("POST", UploadError.http(status: 400, body: "bad")),
            ("POST", UploadError.http(status: 400, body: "bad")),
        ]
        await uploader.upload(record)
        #expect(uploader.methodUsed == .put)
        #expect(server.seen.map(\.method) == ["POST", "POST", "PUT"])
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
    }

    @Test func uploadMissingOnProcessUploadsOnceMore() async throws {
        let record = try take(bytes: 500)
        await api.enqueueProcess(.failure(APIError(status: 409, code: .uploadMissing, message: "no video", retryable: false)))
        await uploader.upload(record)
        #expect(server.seen.map(\.method) == ["PUT", "PUT"])
        let processCalls = await api.calls.filter { if case .processRecipe = $0 { true } else { false } }
        #expect(processCalls.count == 2)
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
    }

    @Test func aRefusedUploadKeepsTheTakeAndARetryReusesTheRecipe() async throws {
        let record = try take(bytes: 500)
        server.putStatus = 403
        await uploader.upload(record)
        guard case .failed = uploader.phase else {
            Issue.record("expected failed, got \(uploader.phase)")
            return
        }
        #expect(server.seen.count == 1, "403 is not retried")
        #expect(FileManager.default.fileExists(atPath: store.videoURL(for: record.id).path))
        let saved = try #require(store.pending().first)
        #expect(saved.upload != nil, "the created recipe is remembered")

        server.putStatus = 200
        await uploader.upload(saved)
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
        let creates = await api.calls.filter { if case .createRecipe = $0 { true } else { false } }
        #expect(creates.count == 1, "no second recipe")
    }

    @Test func serverErrorsAreRetriedWithTheBackoff() async throws {
        let record = try take(bytes: 500)
        server.failures = [
            ("PUT", UploadError.http(status: 503, body: "")), ("PUT", URLError(.timedOut)),
        ]
        await uploader.upload(record)
        #expect(server.seen.map(\.method) == ["PUT", "PUT", "PUT"])
        #expect(clock.sleeps == [.seconds(3), .seconds(5)])
        if case .done = uploader.phase {} else { Issue.record("expected done, got \(uploader.phase)") }
    }
}

// MARK: - Take store

@Suite("Take store")
struct TakeStoreTests {
    @Test func pendingListsUnprocessedTakesWithAFile() throws {
        let store = tempStore()
        try store.prepare()
        var a = TakeRecord(id: "a", source: .phone, recordedAt: Date(timeIntervalSince1970: 1), durationS: 1, stepMarksS: [], consent: true)
        var b = a
        b.id = "b"
        b.recordedAt = Date(timeIntervalSince1970: 2)
        var c = a
        c.id = "c"
        c.processedAt = Date()
        for r in [a, b, c] {
            try Data("x".utf8).write(to: store.videoURL(for: r.id))
            try store.save(r)
        }
        a.title = "t"
        try store.save(a)
        #expect(store.pending().map(\.id) == ["b", "a"], "newest first, processed excluded")
        try FileManager.default.removeItem(at: store.videoURL(for: "b"))
        #expect(store.pending().map(\.id) == ["a"], "a record without its video is not pending")
        store.delete("a")
        #expect(store.pending().isEmpty)
    }
}

// MARK: - MP4 writer (08.3)

private func bgraFrame(_ width: Int, _ height: Int, shade: UInt8) throws -> CVPixelBuffer {
    var buffer: CVPixelBuffer?
    let attributes: [String: Any] = [kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any]()]
    CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, attributes as CFDictionary, &buffer)
    let b = try #require(buffer)
    CVPixelBufferLockBaseAddress(b, [])
    memset(CVPixelBufferGetBaseAddress(b), Int32(shade), CVPixelBufferGetDataSize(b))
    CVPixelBufferUnlockBaseAddress(b, [])
    return b
}

/// 0.1 s of a 440 Hz tone, 44.1 kHz mono 16-bit, at `time`.
private func audioSample(at time: CMTime) throws -> CMSampleBuffer {
    let rate = 44_100
    let frames = rate / 10
    var asbd = AudioStreamBasicDescription(
        mSampleRate: Float64(rate), mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked,
        mBytesPerPacket: 2, mFramesPerPacket: 1, mBytesPerFrame: 2, mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0)
    var format: CMAudioFormatDescription?
    CMAudioFormatDescriptionCreate(allocator: kCFAllocatorDefault, asbd: &asbd, layoutSize: 0, layout: nil,
                                   magicCookieSize: 0, magicCookie: nil, extensions: nil, formatDescriptionOut: &format)
    let step = 2 * Double.pi * 440 / Double(rate)
    var samples: [Int16] = (0..<frames).map { (i: Int) -> Int16 in
        let phase: Double = Double(i) * step
        return Int16(sin(phase) * 8000)
    }
    var block: CMBlockBuffer?
    let bytes = frames * 2
    CMBlockBufferCreateWithMemoryBlock(allocator: kCFAllocatorDefault, memoryBlock: nil, blockLength: bytes,
                                       blockAllocator: kCFAllocatorDefault, customBlockSource: nil, offsetToData: 0,
                                       dataLength: bytes, flags: 0, blockBufferOut: &block)
    let blockBuffer = try #require(block)
    _ = samples.withUnsafeMutableBytes { CMBlockBufferReplaceDataBytes(with: $0.baseAddress!, blockBuffer: blockBuffer, offsetIntoDestination: 0, dataLength: bytes) }
    var sample: CMSampleBuffer?
    CMAudioSampleBufferCreateReadyWithPacketDescriptions(
        allocator: kCFAllocatorDefault, dataBuffer: blockBuffer, formatDescription: try #require(format),
        sampleCount: frames, presentationTimeStamp: time, packetDescriptions: nil, sampleBufferOut: &sample)
    return try #require(sample)
}

@Suite("Take writer")
struct TakeWriterTests {
    @Test func writesTwoSecondsOfVideoAndAudioInSync() async throws {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("take-\(UUID().uuidString).mp4")
        defer { try? FileManager.default.removeItem(at: url) }
        let writer = TakeWriter(url: url)
        let start = CMTime(seconds: 1000, preferredTimescale: 600)
        // Audio that starts before the first frame is dropped.
        writer.appendAudio(try audioSample(at: CMTimeSubtract(start, CMTime(seconds: 0.5, preferredTimescale: 600))))
        for i in 0..<48 {  // 2 s at 24 fps
            let t = CMTimeAdd(start, CMTime(value: CMTimeValue(i * 25), timescale: 600))
            writer.appendVideo(try bgraFrame(320, 240, shade: UInt8(i * 5)), at: t)
            if i % 2 == 0, i < 46 {
                writer.appendAudio(try audioSample(at: CMTimeAdd(start, CMTime(seconds: Double(i) / 24, preferredTimescale: 600))))
            }
            try await Task.sleep(for: .milliseconds(41))  // real-time input at 24 fps, as on the device
        }
        let result = try await writer.finish()
        #expect(result.videoFrames >= 40, "a few frames may be dropped under load: \(result.videoFrames)")
        #expect(result.width == 320 && result.height == 240)
        #expect(result.hasAudio)
        #expect(abs(result.durationS - 2.0) < 0.15, "duration \(result.durationS)")

        let asset = AVURLAsset(url: url)
        let duration = try await asset.load(.duration).seconds
        #expect(abs(duration - 2.0) < 0.2, "file duration \(duration)")
        #expect(try await asset.loadTracks(withMediaType: .video).count == 1)
        #expect(try await asset.loadTracks(withMediaType: .audio).count == 1)
    }

    @Test func noFramesMeansNoVideoError() async {
        let writer = TakeWriter(url: FileManager.default.temporaryDirectory.appendingPathComponent("empty-\(UUID().uuidString).mp4"))
        await #expect(throws: TakeWriter.WriterError.noVideo) { _ = try await writer.finish() }
    }
}
