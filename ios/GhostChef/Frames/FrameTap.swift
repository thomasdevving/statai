import CoreVideo
import Foundation

/// Lets Chef mode receive every camera frame (IOS-08.3) while the cook-along keeps using only the
/// newest one. Set from any thread, called on the camera's frame thread.
final class FrameTap: @unchecked Sendable {
    private let lock = NSLock()
    private var handler: (@Sendable (CVPixelBuffer) -> Void)?

    func set(_ handler: (@Sendable (CVPixelBuffer) -> Void)?) {
        lock.withLock { self.handler = handler }
    }

    var isActive: Bool { lock.withLock { handler != nil } }

    func emit(_ buffer: CVPixelBuffer) {
        let handler = lock.withLock { self.handler }
        handler?(buffer)
    }
}
