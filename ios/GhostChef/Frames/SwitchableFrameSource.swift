import Foundation

/// A frame source that can be swapped mid-session (IOS-07.4): the cook-along keeps one
/// `FrameSource`, and "Continue with phone camera" / the glasses coming back only change what is
/// behind it. The session state (step, timers, watcher) is untouched.
final class SwitchableFrameSource: FrameSource, @unchecked Sendable {
    private let lock = NSLock()
    private var _current: any FrameSource
    private(set) var currentKind: FrameSourceKind

    init(_ source: any FrameSource, kind: FrameSourceKind) {
        _current = source
        currentKind = kind
    }

    var current: any FrameSource { lock.withLock { _current } }

    /// Starts the new source, then stops the old one. On failure the old source stays.
    func switchTo(_ source: any FrameSource, kind: FrameSourceKind) async throws {
        let old = current
        guard old !== source else { return }
        try await source.start()
        lock.withLock {
            _current = source
            currentKind = kind
        }
        old.stop()
    }

    var isAvailable: Bool { current.isAvailable }
    func start() async throws { try await current.start() }
    func stop() { current.stop() }
    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? {
        await current.latestJPEG(maxLongEdge: maxLongEdge, quality: quality)
    }
}
