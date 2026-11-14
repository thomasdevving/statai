import CoreVideo
import Foundation

/// Holds only the newest camera frame from the glasses (IOS-06.2). Written on the SDK's frame
/// callback thread, read by `DATFrameSource` when a check or watch needs a JPEG.
/// Keeping one pixel buffer (and dropping the rest) also keeps the SDK's buffer pool from running dry.
final class LatestFrameStore: @unchecked Sendable {
    private let lock = NSLock()
    private var pixels: CVPixelBuffer?
    private var receivedAt: Date?
    private let now: @Sendable () -> Date

    init(now: @escaping @Sendable () -> Date = { Date() }) {
        self.now = now
    }

    func put(_ buffer: CVPixelBuffer) {
        let at = now()
        lock.withLock {
            pixels = buffer
            receivedAt = at
        }
    }

    func clear() {
        lock.withLock {
            pixels = nil
            receivedAt = nil
        }
    }

    /// The newest frame if it is younger than `FrameFreshness.maxAge`, else nil.
    func freshFrame() -> CVPixelBuffer? {
        let t = now()
        return lock.withLock {
            FrameFreshness.isFresh(receivedAt: receivedAt, now: t) ? pixels : nil
        }
    }

    var hasFreshFrame: Bool {
        let t = now()
        return lock.withLock { FrameFreshness.isFresh(receivedAt: receivedAt, now: t) && pixels != nil }
    }

    var lastReceivedAt: Date? { lock.withLock { receivedAt } }
}
