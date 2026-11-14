import CoreImage
import CoreMedia
import Foundation
import MWDATCamera
import MWDATCore
import MWDATDisplay
import MWDATInputs
import MWDATMockDevice
import Observation
import UIKit

/// Owns the Meta Wearables DAT SDK for the app: registration, device state, one `DeviceSession`,
/// and the IOS-02 proofs a–e. Runs against real glasses or against MockDeviceKit.
///
/// API usage follows the SDK 1.0.1 docs and the CameraAccess / DisplayAccess / BirdSpotter samples.
@MainActor
@Observable
final class GlassesManager {
    // MARK: Proofs

    enum Proof: String, CaseIterable, Identifiable {
        case a, b, c, d, e
        var id: String { rawValue }

        var title: String {
            switch self {
            case .a: "Find the glasses"
            case .b: "One camera frame"
            case .c: "Card in the lens"
            case .d: "Camera + display together"
            case .e: "Inputs reach the app"
            }
        }

        var passWhen: String {
            switch self {
            case .a: "A device appears that supports a display"
            case .b: "A frame arrives and becomes a JPEG"
            case .c: "Image + two lines show on the display"
            case .d: "Frames keep arriving while the card updates every 5 s for 60 s"
            case .e: "The log prints each input event"
            }
        }
    }

    enum Outcome: Equatable {
        case notRun
        case running(String)
        case pass(String)
        case fail(String)

        var isRunning: Bool {
            if case .running = self { return true }
            return false
        }
    }

    struct LogLine: Identifiable, Equatable {
        let id = UUID()
        let at: Date
        let text: String
    }

    struct DeviceRow: Identifiable, Equatable {
        let id: String
        let name: String
        let type: String
        let link: String
        let compatibility: String
        let supportsDisplay: Bool
    }

    enum MockFeed: String, CaseIterable, Identifiable {
        case phoneCamera, sampleVideo
        var id: String { rawValue }
        var label: String {
            switch self {
            case .phoneCamera: "Phone back camera"
            case .sampleVideo: "Sample video"
            }
        }
    }

    // MARK: Observable state

    private(set) var configured = false
    private(set) var configureError: String?
    private(set) var registration = "unknown"
    private(set) var devices: [DeviceRow] = []
    private(set) var sessionState: DeviceSessionState = .idle
    private(set) var displayState: String = "—"
    private(set) var outcomes: [Proof: Outcome] = Dictionary(
        uniqueKeysWithValues: Proof.allCases.map { ($0, .notRun) })
    private(set) var log: [LogLine] = []
    private(set) var lastFrame: UIImage?
    private(set) var lastFrameInfo: String?
    private(set) var framesReceived = 0
    private(set) var inputEventsReceived = 0

    // Mock device
    private(set) var mockEnabled = false
    private(set) var mockPaired = false
    var mockFeed: MockFeed = {
        #if targetEnvironment(simulator)
            .sampleVideo
        #else
            .phoneCamera
        #endif
    }()
    /// MockDeviceKit's rendering of what the glasses display would show.
    private(set) var mockDisplayPreview: UIView?

    // MARK: SDK handles

    @ObservationIgnored private var selector: AutoDeviceSelector?
    @ObservationIgnored private var session: DeviceSession?
    @ObservationIgnored private var camera: MWDATCamera.Camera?
    @ObservationIgnored private var display: Display?
    @ObservationIgnored private var inputs: Inputs?
    @ObservationIgnored private var mockGlasses: (any MockGlasses)?
    @ObservationIgnored private let sessionTokens = ListenerTokenBag()
    @ObservationIgnored private let cameraTokens = ListenerTokenBag()
    @ObservationIgnored private let displayTokens = ListenerTokenBag()
    @ObservationIgnored private var deviceTokens: [any AnyListenerToken] = []
    @ObservationIgnored private var tasks: [Task<Void, Never>] = []
    @ObservationIgnored private var inputDrain: Task<Void, Never>?
    @ObservationIgnored private var proofD: Task<Void, Never>?
    @ObservationIgnored private let frames = FrameCounter()
    @ObservationIgnored private var displayIsStarted = false

    // MARK: Setup

    /// Call once at launch (SDK rule: `Wearables.configure()` before anything else).
    func configure() {
        guard !configured else { return }
        do {
            try Wearables.configure()
            configured = true
            note("SDK configured")
        } catch {
            configureError = error.localizedDescription
            note("SDK configure failed: \(error.localizedDescription)")
            return
        }
        selector = AutoDeviceSelector(wearables: Wearables.shared)
        mockEnabled = MockDeviceKit.shared.isEnabled
        observeRegistration()
        observeDevices()
    }

    /// Meta AI calls back into the app after registration and permission flows.
    func handle(url: URL) {
        guard
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
            components.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true
        else { return }
        Task {
            do {
                _ = try await Wearables.shared.handleUrl(url)
                note("Meta AI callback handled")
            } catch {
                note("Meta AI callback failed: \(error.localizedDescription)")
            }
        }
    }

    /// Opens the Meta AI app to register Ghost Chef (real glasses only).
    func register() async {
        do {
            try await Wearables.shared.startRegistration()
            note("Registration started in Meta AI")
        } catch {
            note("Registration failed: \(error.localizedDescription)")
        }
    }

    private func observeRegistration() {
        tasks.append(
            Task { [weak self] in
                for await state in Wearables.shared.registrationStateStream() {
                    let name = Self.describe(state)
                    self?.registration = name
                    self?.note("Registration: \(name)")
                }
            })
    }

    private static func describe(_ state: RegistrationState) -> String {
        switch state {
        case .unavailable: "unavailable"
        case .available: "available (not registered)"
        case .registering: "registering"
        case .registered: "registered"
        @unknown default: "unknown (\(state))"
        }
    }

    private func observeDevices() {
        tasks.append(
            Task { [weak self] in
                for await ids in Wearables.shared.devicesStream() {
                    guard let self else { return }
                    for token in deviceTokens { await token.cancel() }
                    deviceTokens = []
                    let list = ids.compactMap { Wearables.shared.deviceForIdentifier($0) }
                    publish(list)
                    for device in list {
                        deviceTokens.append(
                            device.addLinkStateListener { [weak self] _ in
                                Task { @MainActor in self?.publish(list) }
                            })
                        deviceTokens.append(
                            device.addCompatibilityListener { [weak self] _ in
                                Task { @MainActor in self?.publish(list) }
                            })
                    }
                }
            })
    }

    private func publish(_ list: [Device]) {
        devices = list.map {
            DeviceRow(
                id: $0.identifier, name: $0.nameOrId(), type: String(describing: $0.deviceType()),
                link: String(describing: $0.linkState), compatibility: String(describing: $0.compatibility()),
                supportsDisplay: $0.supportsDisplay())
        }
    }

    // MARK: MockDeviceKit

    /// Enables MockDeviceKit (registered, permissions granted) and pairs simulated
    /// Meta Ray-Ban Display glasses that are powered on, unfolded and worn.
    func pairMockDisplayGlasses() async {
        let kit = MockDeviceKit.shared
        if !kit.isEnabled {
            kit.enable(config: MockDeviceKitConfig(initiallyRegistered: true, initialPermissionsGranted: true))
        }
        mockEnabled = true
        if let mockGlasses {
            note("Mock glasses already paired (\(mockGlasses.deviceIdentifier))")
            return
        }
        do {
            let glasses = try kit.pairGlasses(model: .metaRayBanDisplay)
            mockGlasses = glasses
            glasses.powerOn()
            glasses.unfold()
            glasses.don()
            // A mock pair streaming with no feed set crashes (BirdSpotter sample note), so set one now.
            await applyMockFeed(to: glasses)
            mockDisplayPreview = glasses.services.display.createPreviewView()
            mockPaired = true
            note("Mock Meta Ray-Ban Display paired: \(glasses.deviceIdentifier)")
        } catch {
            note("Mock pairing failed: \(error)")
        }
    }

    func setMockFeed(_ feed: MockFeed) async {
        mockFeed = feed
        if let mockGlasses { await applyMockFeed(to: mockGlasses) }
    }

    private func applyMockFeed(to glasses: any MockGlasses) async {
        switch mockFeed {
        case .sampleVideo:
            guard let url = Bundle.main.url(forResource: "mock-feed", withExtension: "mp4") else {
                note("Sample video missing from the bundle")
                return
            }
            glasses.services.camera.setCameraFeed(fileURL: url)
            note("Mock camera feed: sample video")
        case .phoneCamera:
            guard await AVCaptureAccess.request() else {
                note("Phone camera access denied; mock feed not set")
                return
            }
            glasses.services.camera.setCameraFeed(cameraFacing: .back)
            note("Mock camera feed: phone back camera")
        }
    }

    func disableMock() async {
        await tearDown()
        await MockDeviceKit.shared.disable()
        mockGlasses = nil
        mockDisplayPreview = nil
        mockPaired = false
        mockEnabled = false
        note("MockDeviceKit disabled")
    }

    /// Injects input events through the mock glasses (they are dropped unless Inputs is attached).
    func injectMockInputs() {
        guard let input = mockGlasses?.services.input else { return }
        input.select()
        input.navRight()
        input.back()
        note("Injected mock inputs: select, nav right, back")
    }

    /// Pairs mock Display glasses and runs proofs a, b, c, e, then d, one after another.
    /// Results belong in the MockDeviceKit column only.
    func runAllOnMock(dSeconds: Int = 60) async {
        note("=== Run all on MockDeviceKit ===")
        await pairMockDisplayGlasses()
        await runA()
        await runB()
        await runC()
        await runE()
        await performD(seconds: dSeconds)
        let summary = Proof.allCases.map { proof -> String in
            switch outcomes[proof] ?? .notRun {
            case .pass: "\(proof.rawValue)=PASS"
            case .fail: "\(proof.rawValue)=FAIL"
            default: "\(proof.rawValue)=—"
            }
        }
        note("=== Summary (mock): \(summary.joined(separator: " ")) ===")
    }

    // MARK: Proof a: registration and discovery

    func runA() async {
        set(.a, .running("Looking for glasses…"))
        let found = await waitUntil(seconds: 8) { !self.devices.isEmpty }
        guard found else {
            set(.a, .fail("No device after 8 s. Registration: \(registration). Pair mock glasses or register with Meta AI."))
            return
        }
        let rows = devices.map { "\($0.name) [\($0.type)] link \($0.link), \($0.compatibility), display \($0.supportsDisplay)" }
        if devices.contains(where: \.supportsDisplay) {
            set(.a, .pass(rows.joined(separator: "; ")))
        } else {
            set(.a, .fail("Found, but none supports a display: " + rows.joined(separator: "; ")))
        }
    }

    // MARK: Proof b: one camera frame

    func runB() async {
        set(.b, .running("Starting session…"))
        guard let session = await ensureSession() else {
            set(.b, .fail("Session did not start (state \(sessionState))"))
            return
        }
        do {
            if try await Wearables.shared.checkPermissionStatus(.camera) != .granted {
                set(.b, .running("Asking for camera permission in Meta AI…"))
                guard try await Wearables.shared.requestPermission(.camera) == .granted else {
                    set(.b, .fail("Camera permission denied"))
                    return
                }
            }
        } catch {
            set(.b, .fail("Permission check failed: \(error.localizedDescription)"))
            return
        }
        if camera == nil, !startCamera(on: session) {
            set(.b, .fail("Could not add the camera to the session"))
            return
        }
        set(.b, .running("Waiting for a frame…"))
        let requested = Date()
        frames.requestSnapshot()
        let gotFrame = await waitUntil(seconds: 10) { self.lastFrameInfo != nil && self.frames.lastSnapshotAt ?? .distantPast >= requested }
        if gotFrame, let info = lastFrameInfo {
            set(.b, .pass(info))
        } else {
            set(.b, .fail("No frame within 10 s (frames received: \(framesReceived))"))
        }
    }

    /// Grabs another JPEG from the running stream (Lab button).
    func grabFrame() {
        frames.requestSnapshot()
    }

    @discardableResult
    private func startCamera(on session: DeviceSession) -> Bool {
        let config = StreamConfiguration(videoCodec: .raw, resolution: .high, frameRate: 24)
        do {
            guard let newCamera = try session.addCamera(config: config) else { return false }
            camera = newCamera
            let stream = newCamera.stream
            stream.statePublisher.listen { [weak self] state in
                Task { @MainActor in self?.note("Stream: \(state)") }
            }.store(in: cameraTokens)
            stream.errorPublisher.listen { [weak self] error in
                Task { @MainActor in self?.note("Stream error: \(error.localizedDescription)") }
            }.store(in: cameraTokens)
            let counter = frames
            stream.videoFramePublisher.listen { [weak self] frame in
                let total = counter.increment()
                guard let requestedAt = counter.takeSnapshotRequest(),
                    let pixels = CMSampleBufferGetImageBuffer(frame.sampleBuffer)
                else {
                    if total % 24 == 0 { Task { @MainActor in self?.framesReceived = total } }
                    return
                }
                let width = CVPixelBufferGetWidth(pixels)
                let height = CVPixelBufferGetHeight(pixels)
                let jpeg = JPEGEncoder.encode(CIImage(cvPixelBuffer: pixels), maxLongEdge: 1280, quality: 0.8)
                let elapsed = Date().timeIntervalSince(requestedAt)
                counter.markSnapshot()
                Task { @MainActor in
                    self?.framesReceived = total
                    self?.receiveSnapshot(jpeg, width: width, height: height, latency: elapsed)
                }
            }.store(in: cameraTokens)
            stream.start()
            note("Camera stream starting: raw, high, 24 fps")
            return true
        } catch {
            note("addCamera failed: \(error.localizedDescription)")
            return false
        }
    }

    private func receiveSnapshot(_ jpeg: Data?, width: Int, height: Int, latency: TimeInterval) {
        guard let jpeg, let image = UIImage(data: jpeg) else {
            note("Frame \(width)×\(height) could not be encoded as JPEG")
            return
        }
        lastFrame = image
        let size = JPEGEncoder.pixelSize(of: jpeg) ?? .zero
        lastFrameInfo =
            "Stream frame \(width)×\(height) → JPEG \(Int(size.width))×\(Int(size.height)), "
            + "\(jpeg.count.formatted(.byteCount(style: .file))), "
            + "\(Int(latency * 1000)) ms from request"
        note(lastFrameInfo!)
    }

    // MARK: Proof c: card in the lens

    func runC() async {
        set(.c, .running("Starting display…"))
        guard let display = await ensureDisplay() else {
            if case .running = outcomes[.c] { set(.c, .fail("Display did not start (state \(displayState))")) }
            return
        }
        let step = try? FixtureRecipe.load().steps.first { $0.idx == 3 }
        let card = GlassesCards.stepCard(
            index: step?.idx ?? 4, total: 6, title: step?.title ?? "Add fillings",
            keyLine: step?.keyLine ?? "One even layer, edge to edge",
            image: GlassesCards.loadThumbnail(step?.refImageURL))
        do {
            try await display.send(card)
            set(.c, .pass("Card sent: image + title + key line. Check the display\(mockPaired ? " preview" : "")."))
        } catch {
            set(.c, .fail("send failed: \((error as? DisplayError)?.description ?? error.localizedDescription)"))
        }
    }

    private func ensureDisplay() async -> Display? {
        if let display, displayIsStarted { return display }
        guard let session = await ensureSession() else { return nil }
        if let deviceID = selector?.activeDevice,
            let device = Wearables.shared.deviceForIdentifier(deviceID), !device.supportsDisplay()
        {
            set(.c, .fail("This device has no display"))
            return nil
        }
        do {
            let capability = try session.addDisplay()
            display = capability
            capability.statePublisher.listen { [weak self] state in
                Task { @MainActor in
                    self?.displayState = String(describing: state)
                    self?.displayIsStarted = state == .started
                    self?.note("Display: \(state)")
                }
            }.store(in: displayTokens)
            capability.start()
        } catch {
            note("addDisplay failed: \(error.localizedDescription)")
            return nil
        }
        guard await waitUntil(seconds: 10, { self.displayIsStarted }) else { return nil }
        return display
    }

    // MARK: Proof d: camera + display together

    func runD(seconds: Int = 60) {
        proofD?.cancel()
        proofD = Task { [weak self] in await self?.performD(seconds: seconds) }
    }

    func cancelD() {
        proofD?.cancel()
        if outcomes[.d]?.isRunning == true { set(.d, .fail("Cancelled")) }
    }

    private func performD(seconds: Int) async {
        set(.d, .running("Starting camera and display…"))
        if camera == nil { await runB() }
        guard camera != nil, let display = await ensureDisplay() else {
            set(.d, .fail("Needs proofs b and c working first"))
            return
        }
        let step = try? FixtureRecipe.load().steps.first { $0.idx == 3 }
        let image = GlassesCards.loadThumbnail(step?.refImageURL)
        var windows: [Int] = []
        var sendFailures = 0
        var last = frames.count
        for elapsed in stride(from: 5, through: seconds, by: 5) {
            try? await Task.sleep(for: .seconds(5))
            if Task.isCancelled { return }
            let now = frames.count
            windows.append(now - last)
            last = now
            let fps = Double(windows.last ?? 0) / 5
            set(.d, .running("\(elapsed)/\(seconds) s · \(now) frames · \(String(format: "%.1f", fps)) fps"))
            do {
                try await display.send(
                    GlassesCards.stepCard(
                        index: 4, total: 6, title: step?.title ?? "Add fillings",
                        keyLine: "Update \(elapsed / 5): \(String(format: "%.0f", fps)) fps", image: image,
                        footer: "\(elapsed) s · \(now) frames"))
            } catch {
                sendFailures += 1
                note("Card update \(elapsed / 5) failed: \(error.localizedDescription)")
            }
        }
        let fpsList = windows.map { String(format: "%.1f", Double($0) / 5) }.joined(separator: ", ")
        if windows.allSatisfy({ $0 > 0 }) && sendFailures == 0 {
            set(.d, .pass("\(seconds) s: frames every window (fps per 5 s: \(fpsList)); \(windows.count) card updates, 0 failed"))
        } else {
            set(.d, .fail("fps per 5 s: \(fpsList); card update failures: \(sendFailures)"))
        }
    }

    // MARK: Proof e: inputs

    func runE() async {
        set(.e, .running("Attaching inputs…"))
        guard let session = await ensureSession() else {
            set(.e, .fail("Session did not start"))
            return
        }
        if inputs == nil {
            do {
                guard let attached = try session.addInputs(configuration: InputsConfiguration()) else {
                    set(.e, .fail("addInputs returned nil: this device reports no inputs"))
                    return
                }
                inputs = attached
                let events = attached.events
                inputDrain = Task { [weak self] in
                    for await event in events {
                        self?.inputEventsReceived += 1
                        self?.note("Input: \(event)")
                    }
                    self?.note("Input event stream ended")
                }
            } catch {
                set(.e, .fail("addInputs failed: \(error.localizedDescription)"))
                return
            }
        }
        if let display = await ensureDisplayIfSupported() {
            try? await display.send(
                GlassesCards.inputCard(
                    onCheck: { [weak self] in Task { @MainActor in self?.note("Display button: Check") } },
                    onNext: { [weak self] in Task { @MainActor in self?.note("Display button: Next") } }))
        }
        let before = inputEventsReceived
        if mockPaired {
            try? await Task.sleep(for: .milliseconds(500))
            injectMockInputs()
            set(.e, .running("Injected mock select / nav / back…"))
        } else {
            set(.e, .running("Use the glasses: pinch, swipe, tap, press a button (30 s)…"))
        }
        let arrived = await waitUntil(seconds: mockPaired ? 5 : 30) { self.inputEventsReceived > before }
        if arrived {
            try? await Task.sleep(for: .milliseconds(500))
            let kinds = log.suffix(12).filter { $0.text.hasPrefix("Input:") || $0.text.hasPrefix("Display button") }
                .map { $0.text }
            set(.e, .pass("\(inputEventsReceived - before) event(s): " + kinds.joined(separator: " | ")))
        } else {
            set(.e, .fail("No input event arrived"))
        }
    }

    private func ensureDisplayIfSupported() async -> Display? {
        guard let deviceID = selector?.activeDevice,
            let device = Wearables.shared.deviceForIdentifier(deviceID), device.supportsDisplay()
        else { return nil }
        return await ensureDisplay()
    }

    // MARK: Session

    private func ensureSession() async -> DeviceSession? {
        if let session, sessionState == .started { return session }
        guard configured, let selector else {
            note("SDK not configured")
            return nil
        }
        guard await waitUntil(seconds: 8, { selector.activeDevice != nil }) else {
            note("No active device to open a session on")
            return nil
        }
        do {
            let newSession = try Wearables.shared.createSession(deviceSelector: selector)
            session = newSession
            newSession.statePublisher.listen { [weak self] state in
                Task { @MainActor in
                    self?.sessionState = state
                    self?.note("Session: \(state)")
                    if state == .stopped { self?.sessionStopped() }
                }
            }.store(in: sessionTokens)
            newSession.errorPublisher.listen { [weak self] error in
                Task { @MainActor in self?.note("Session error: \(error.localizedDescription)") }
            }.store(in: sessionTokens)
            try newSession.start()
        } catch {
            note("Session failed: \(error.localizedDescription)")
            return nil
        }
        guard await waitUntil(seconds: 10, { self.sessionState == .started }) else { return nil }
        return session
    }

    private func sessionStopped() {
        inputDrain?.cancel()
        inputDrain = nil
        inputs = nil
        camera = nil
        display = nil
        displayIsStarted = false
        displayState = "—"
        session = nil
        sessionTokens.clear()
        cameraTokens.clear()
        displayTokens.clear()
    }

    /// Stops display, camera and session (Lab "Stop all").
    func tearDown() async {
        proofD?.cancel()
        if let display {
            try? await display.clearDisplay()
            display.stop()
        }
        camera?.stop()
        if inputs != nil { try? session?.removeInputs() }
        session?.stop()
        _ = await waitUntil(seconds: 3) { self.session == nil }
        sessionStopped()
        note("Stopped everything")
    }

    // MARK: Helpers

    private func set(_ proof: Proof, _ outcome: Outcome) {
        outcomes[proof] = outcome
        switch outcome {
        case .pass(let detail): note("PASS \(proof.rawValue): \(detail)")
        case .fail(let detail): note("FAIL \(proof.rawValue): \(detail)")
        default: break
        }
    }

    func note(_ text: String) {
        log.append(LogLine(at: .now, text: text))
        if log.count > 300 { log.removeFirst(log.count - 300) }
        #if DEBUG
            print("[GlassesLab] \(text)")
        #endif
    }

    /// Polls a main-actor condition every 100 ms.
    private func waitUntil(seconds: Double, _ condition: @MainActor () -> Bool) async -> Bool {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(100))
            if Task.isCancelled { return false }
        }
        return condition()
    }
}

/// Counts frames from the SDK's frame callback thread and hands out at most one JPEG
/// snapshot per request.
final class FrameCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var _count = 0
    private var snapshotRequestedAt: Date?
    private var _lastSnapshotAt: Date?

    var count: Int { lock.withLock { _count } }
    var lastSnapshotAt: Date? { lock.withLock { _lastSnapshotAt } }

    func increment() -> Int { lock.withLock { _count += 1; return _count } }
    func requestSnapshot() { lock.withLock { snapshotRequestedAt = Date() } }

    func takeSnapshotRequest() -> Date? {
        lock.withLock {
            defer { snapshotRequestedAt = nil }
            return snapshotRequestedAt
        }
    }

    func markSnapshot() { lock.withLock { _lastSnapshotAt = Date() } }
}

import AVFoundation

enum AVCaptureAccess {
    static func request() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: true
        case .notDetermined: await AVCaptureDevice.requestAccess(for: .video)
        default: false
        }
    }
}
