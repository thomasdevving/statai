import CoreVideo
import Foundation
import Testing

@testable import GhostChef

// IOS-06: the glasses rules that do not need the Meta SDK. Everything that talks to the SDK
// (GlassesManager, GlassesLensRenderer, GlassesCookLink) is verified on MockDeviceKit / glasses.

// MARK: - Status (06.1)

@Suite("Glasses status")
struct GlassesStatusTests {
    private var connected: GlassesStatusInputs {
        GlassesStatusInputs(registered: true, hasDevice: true, link: .connected, supportsDisplay: true)
    }

    @Test func walksFromUnregisteredToReady() {
        var s = GlassesStatusInputs()
        #expect(s.resolve() == .notRegistered)
        s.registered = true
        #expect(s.resolve() == .noDevice)
        s.hasDevice = true
        #expect(s.resolve() == .disconnected("not connected"))
        s.link = .connecting
        #expect(s.resolve() == .connecting)
        s.link = .connected
        #expect(s.resolve() == .ready(displays: false))
        s.supportsDisplay = true
        #expect(s.resolve() == .ready(displays: true))
    }

    @Test func hingesClosedThenOpenRecovers() {
        var s = connected
        s.hingeClosed = true
        #expect(s.resolve() == .disconnected("hinges closed"))
        #expect(!s.resolve().isReady)
        s.hingeClosed = false
        #expect(s.resolve() == .ready(displays: true))
    }

    @Test func configureErrorThermalAndUpdatesWin() {
        var s = connected
        s.thermalCritical = true
        #expect(s.resolve() == .disconnected("too hot"))
        s.thermalCritical = false
        s.compatible = false
        #expect(s.resolve() == .disconnected("update required"))
        s.configureError = "boom"
        #expect(s.resolve() == .unavailable("boom"))
    }

    @Test func sessionStartingIsConnectingAndPausedIsNotReady() {
        var s = connected
        s.session = .starting
        #expect(s.resolve() == .connecting)
        s.session = .paused
        #expect(s.resolve() == .disconnected("paused"))
        s.session = .started
        #expect(s.resolve().isReady && s.resolve().supportsDisplay)
    }
}

// MARK: - Frames (06.2)

private final class TestNow: @unchecked Sendable {
    private let lock = NSLock()
    private var t = Date(timeIntervalSince1970: 1_800_000_000)
    var now: Date { lock.withLock { t } }
    func advance(_ s: TimeInterval) { lock.withLock { t = t.addingTimeInterval(s) } }
}

private func pixelBuffer(width: Int = 720, height: Int = 1280) throws -> CVPixelBuffer {
    var buffer: CVPixelBuffer?
    let attrs = [kCVPixelBufferCGImageCompatibilityKey: true, kCVPixelBufferCGBitmapContextCompatibilityKey: true] as CFDictionary
    let status = CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, attrs, &buffer)
    guard status == kCVReturnSuccess, let buffer else { throw CocoaError(.featureUnsupported) }
    CVPixelBufferLockBaseAddress(buffer, [])
    if let base = CVPixelBufferGetBaseAddress(buffer) {
        // A gradient so the JPEG is not trivially small.
        let bytesPerRow = CVPixelBufferGetBytesPerRow(buffer)
        for y in 0..<height {
            let row = base.advanced(by: y * bytesPerRow).assumingMemoryBound(to: UInt8.self)
            for x in 0..<width {
                row[x * 4] = UInt8(x % 256)
                row[x * 4 + 1] = UInt8(y % 256)
                row[x * 4 + 2] = UInt8((x + y) % 256)
                row[x * 4 + 3] = 255
            }
        }
    }
    CVPixelBufferUnlockBaseAddress(buffer, [])
    return buffer
}

@Suite("Glasses frames")
struct GlassesFrameTests {
    @Test func freshnessIsTwoSeconds() {
        let t = Date(timeIntervalSince1970: 0)
        #expect(FrameFreshness.isFresh(receivedAt: t, now: t.addingTimeInterval(2)))
        #expect(!FrameFreshness.isFresh(receivedAt: t, now: t.addingTimeInterval(2.01)))
        #expect(!FrameFreshness.isFresh(receivedAt: nil, now: t))
    }

    @Test func frameSourceServesTheNewestFrameWithinContractLimits() async throws {
        let clock = TestNow()
        let store = LatestFrameStore(now: { clock.now })
        let source = DATFrameSource(store: store, start: { true }, stop: {})
        #expect(!source.isAvailable)
        #expect(await source.latestJPEG(maxLongEdge: 512, quality: 0.6) == nil)

        store.put(try pixelBuffer())
        #expect(source.isAvailable)
        let watch = try #require(await source.latestJPEG(maxLongEdge: FrameSpec.watch.maxLongEdge, quality: FrameSpec.watch.quality))
        let watchSize = try #require(JPEGEncoder.pixelSize(of: watch))
        #expect(max(watchSize.width, watchSize.height) == 512)
        #expect(watch.count <= FrameSpec.watch.maxBytes)
        let check = try #require(await source.latestJPEG(maxLongEdge: FrameSpec.check.maxLongEdge, quality: FrameSpec.check.quality))
        let checkSize = try #require(JPEGEncoder.pixelSize(of: check))
        #expect(checkSize.width == 720 && checkSize.height == 1280, "portrait and upright, not upscaled")
        #expect(check.count <= FrameSpec.check.maxBytes)
    }

    @Test func staleFramesCountAsNoFrame() async throws {
        let clock = TestNow()
        let store = LatestFrameStore(now: { clock.now })
        let source = DATFrameSource(store: store, start: { true }, stop: {})
        store.put(try pixelBuffer(width: 64, height: 64))
        clock.advance(2.5)
        #expect(!source.isAvailable, "the watcher pauses")
        #expect(await source.latestJPEG(maxLongEdge: 1280, quality: 0.8) == nil, "a check shows Camera not ready")
        store.put(try pixelBuffer(width: 64, height: 64))
        #expect(source.isAvailable)
        store.clear()
        #expect(!source.isAvailable)
    }

    @Test func startFailsWhenTheGlassesCameraDoesNotStart() async {
        let source = DATFrameSource(store: LatestFrameStore(), start: { false }, stop: {})
        await #expect(throws: FrameSourceError.self) { try await source.start() }
    }

    @Test func glassesKindIsSelectable() {
        #expect(FrameSourceKind.selectable.contains(.glasses))
        #expect(FrameSourceKind.glasses.label == "Glasses camera")
    }
}

// MARK: - Inputs (06.4)

@MainActor
@Suite("Glasses inputs")
struct GlassesInputTests {
    @Test func mappingCoversTheFiveInputs() {
        #expect(GlassesInputMapping.input(for: .select) == .primary)
        #expect(GlassesInputMapping.input(for: .navRight) == .next)
        #expect(GlassesInputMapping.input(for: .navLeft) == .previous)
        #expect(GlassesInputMapping.input(for: .back) == .dismiss)
        #expect(GlassesInputMapping.input(for: .navUp) == .showMe)
        #expect(GlassesInputMapping.input(for: .capturePress) == nil, "the capture button stays the system's")
        #expect(GlassesInputMapping.input(for: .drag) == nil)
        #expect(GlassesInputMapping.via(for: .navRight) == .swipe)
        #expect(GlassesInputMapping.via(for: .select) == .pinch)
    }

    @Test func debouncerIgnoresTheSameInputWithin400ms() {
        var d = GlassesInputDebouncer()
        let t = Date(timeIntervalSince1970: 0)
        let results = [
            d.accept(.primary, at: t),
            d.accept(.primary, at: t.addingTimeInterval(0.39)),  // repeat within 400 ms
            d.accept(.next, at: t.addingTimeInterval(0.1)),  // a different input passes at once
            d.accept(.next, at: t.addingTimeInterval(0.6)),
            d.accept(.primary, at: t.addingTimeInterval(1.0)),
        ]
        #expect(results == [true, false, true, true, true])
    }

    @Test func adapterSendsMappedInputsOnceWithVia() {
        var sent: [(CookInput, InputVia)] = []
        var now = Date(timeIntervalSince1970: 0)
        let adapter = GlassesInputAdapter(send: { sent.append(($0, $1)) }, now: { now })
        adapter.handle(.select)
        adapter.handle(.select)  // double-registered pinch
        now = now.addingTimeInterval(0.1)
        adapter.handle(.navRight)
        adapter.handle(.capturePress)
        now = now.addingTimeInterval(0.5)
        adapter.handleDisplayButton(.dismiss)
        #expect(sent.map(\.0) == [.primary, .next, .dismiss])
        #expect(sent.map(\.1) == [.pinch, .swipe, .pinch])
    }
}

// MARK: - Lens layout (06.3)

@Suite("Glasses lens layout")
struct GlassesLensLayoutTests {
    let image = ImageRef(stepID: "s4", fileURL: URL(fileURLWithPath: "/tmp/s4.jpg"))
    var card: StepCard {
        StepCard(idx: 4, total: 6, title: "Add fillings", keyLine: "One even layer, edge to edge", refImage: image, watching: .active)
    }

    @Test func stepCardShowsCounterImageKeyLineWatchingAndButtons() throws {
        let spec = try #require(GlassesLensLayout.card(for: .step(card)))
        #expect(spec.heading == "4/6  Add fillings")
        #expect(spec.lines == ["One even layer, edge to edge"])
        #expect(spec.image == image)
        #expect(spec.meta == "● watching")
        #expect(spec.buttons.map(\.input) == [.primary, .next])
        #expect(spec.icon == nil)
    }

    @Test func fixAndPassDifferByIconAndWordsNotColour() throws {
        let fix = try #require(GlassesLensLayout.card(for: .fix(card, headline: "Filling piled up", fix: "Spread it to the edges", proactive: true)))
        #expect(fix.icon == .warning)
        #expect(fix.heading == "Filling piled up" && fix.lines == ["Spread it to the edges"])
        #expect(fix.meta == "Spotted")
        #expect(fix.buttons.map(\.input) == [.primary, .dismiss])
        let pass = try #require(GlassesLensLayout.card(for: .pass(headline: "Looks right")))
        #expect(pass.icon == .checkmark && pass.image == nil)
        #expect(GlassesCardSpec.Icon.warning != .checkmark)
    }

    @Test func everyScreenHasACardWithAtMostTwoLines() {
        let screens: [LensScreen] = [
            .recipePick(titles: ["Ham and cheese sandwich"], selected: 0), .recipePick(titles: [], selected: 0),
            .step(card), .checking(card), .pass(headline: ""),
            .fix(card, headline: "Edges left bare", fix: "Spread right to the crust", proactive: false),
            .unsure(headline: "Can't tell", hint: "Look straight down at the board"),
            .talking(phase: .listening, caption: ""), .talking(phase: .answering, caption: "So every bite has filling"),
            .showMe(card), .timer(remainingS: 90, card), .done(nil),
            .done(SessionSummary(stepsTotal: 6, stepsPassedFirstTry: 4, fixesCaught: 2, warnings: 1, questions: 1)),
            .notice("No connection"),
        ]
        for screen in screens {
            let spec = GlassesLensLayout.card(for: screen)
            #expect(spec != nil, "\(screen)")
            #expect((spec?.lines.count ?? 0) <= 2, "\(screen)")
            #expect(!(spec?.heading.isEmpty ?? true), "\(screen)")
        }
    }

    @Test func talkingDoneAndWatchingTexts() throws {
        let talk = try #require(GlassesLensLayout.card(for: .talking(phase: .answering, caption: "So every bite")))
        #expect(talk.icon == .speech && talk.heading == "Answering" && talk.lines == ["So every bite"])
        let done = try #require(GlassesLensLayout.card(for: .done(SessionSummary(stepsTotal: 6, stepsPassedFirstTry: 4, fixesCaught: 2, warnings: 0, questions: 0))))
        #expect(done.lines == ["4 of 6 first try · 2 fixes caught"])
        #expect(GlassesLensLayout.watchingText(.off) == nil)
        #expect(GlassesLensLayout.watchingText(.offline) == "○ offline")
    }

    @Test func buttonsCanBeTurnedOff() throws {
        let spec = try #require(GlassesLensLayout.card(for: .step(card), withButtons: false))
        #expect(spec.buttons.isEmpty)
    }
}

// MARK: - Display throttle (06.3)

@Suite("Glasses display throttle")
struct GlassesDisplayThrottleTests {
    let a = GlassesCardSpec(icon: nil, heading: "A", lines: [], image: nil, meta: nil, buttons: [])
    let b = GlassesCardSpec(icon: nil, heading: "B", lines: [], image: nil, meta: nil, buttons: [])
    let t = Date(timeIntervalSince1970: 0)

    @Test func sendsOnChangeAtMostTwiceASecond() {
        var throttle = GlassesDisplayThrottle()
        #expect(throttle.plan(for: a, now: t) == .sendNow)
        throttle.didSend(a, at: t)
        #expect(throttle.plan(for: a, now: t.addingTimeInterval(5)) == .skip, "unchanged: nothing sent")
        guard case .sendAfter(let wait) = throttle.plan(for: b, now: t.addingTimeInterval(0.2)) else {
            Issue.record("a change within 0.5 s should be delayed")
            return
        }
        #expect(abs(wait - 0.3) < 0.001)
        #expect(throttle.plan(for: b, now: t.addingTimeInterval(0.5)) == .sendNow)
    }

    @Test func clearIsNeverDelayedAndNotRepeated() {
        var throttle = GlassesDisplayThrottle()
        throttle.didSend(a, at: t)
        #expect(throttle.plan(for: nil, now: t.addingTimeInterval(0.1)) == .sendNow)
        throttle.didSend(nil, at: t.addingTimeInterval(0.1))
        #expect(throttle.plan(for: nil, now: t.addingTimeInterval(0.2)) == .skip)
        throttle.reset()
        #expect(throttle.plan(for: a, now: t.addingTimeInterval(0.3)) == .sendNow)
    }
}
