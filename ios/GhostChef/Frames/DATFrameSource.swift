import CoreImage
import Foundation

/// `FrameSource` on the glasses' camera stream (IOS-06.2). Everything downstream (checks, the
/// watcher) is unchanged: it only ever sees JPEGs.
///
/// Frames older than 2 s count as no frame: `isAvailable` turns false (the watcher pauses) and
/// `latestJPEG` returns nil (a check shows "Camera not ready").
final class DATFrameSource: FrameSource, @unchecked Sendable {
    private let store: LatestFrameStore
    private let startStream: @MainActor () async -> Bool
    private let stopStream: @MainActor () async -> Void

    init(
        store: LatestFrameStore, start: @escaping @MainActor () async -> Bool,
        stop: @escaping @MainActor () async -> Void
    ) {
        self.store = store
        startStream = start
        stopStream = stop
    }

    var isAvailable: Bool { store.hasFreshFrame }

    func start() async throws {
        guard await startStream() else {
            throw FrameSourceError.configurationFailed("The glasses camera did not start. Check the glasses status in Settings.")
        }
    }

    func stop() {
        let stopStream = stopStream
        Task { @MainActor in await stopStream() }
    }

    /// The glasses stream arrives upright (720×1280 portrait on the mock), so no rotation.
    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? {
        guard let pixels = store.freshFrame() else { return nil }
        return JPEGEncoder.encode(CIImage(cvPixelBuffer: pixels), maxLongEdge: maxLongEdge, quality: quality)
    }
}
