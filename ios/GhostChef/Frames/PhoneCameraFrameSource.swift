@preconcurrency import AVFoundation
import CoreImage
import Foundation

/// The iPhone's back wide camera as a `FrameSource`.
///
/// Frames arrive on a background queue; only the most recent pixel buffer is kept. JPEG encoding
/// runs on a separate background queue, so nothing here blocks the main actor.
final class PhoneCameraFrameSource: NSObject, FrameSource, @unchecked Sendable {
    /// For `CameraPreview`. Configure and run it only through this class.
    let captureSession = AVCaptureSession()

    private let sessionQueue = DispatchQueue(label: "ghostchef.camera.session")
    private let bufferQueue = DispatchQueue(label: "ghostchef.camera.buffers")
    private let encodeQueue = DispatchQueue(label: "ghostchef.camera.encode", qos: .userInitiated)
    private let output = AVCaptureVideoDataOutput()

    private let lock = NSLock()
    private var latestBuffer: CVPixelBuffer?  // guarded by `lock`
    private var configured = false  // touched only on `sessionQueue`

    var isAvailable: Bool {
        guard AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) != nil
        else { return false }
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        return status != .denied && status != .restricted
    }

    func start() async throws {
        guard await AVCaptureDevice.requestAccess(for: .video) else {
            throw FrameSourceError.permissionDenied
        }
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, any Error>) in
            sessionQueue.async { [self] in
                do {
                    try configureIfNeeded()
                    if !captureSession.isRunning { captureSession.startRunning() }
                    cont.resume()
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    func stop() {
        sessionQueue.async { [self] in
            if captureSession.isRunning { captureSession.stopRunning() }
        }
        lock.withLock { latestBuffer = nil }
    }

    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? {
        guard let buffer = lock.withLock({ latestBuffer }) else { return nil }
        nonisolated(unsafe) let pixels = buffer
        return await withCheckedContinuation { cont in
            encodeQueue.async {
                let image = CIImage(cvPixelBuffer: pixels)
                cont.resume(returning: JPEGEncoder.encode(image, maxLongEdge: maxLongEdge, quality: quality))
            }
        }
    }

    // MARK: - Configuration (sessionQueue only)

    private func configureIfNeeded() throws {
        guard !configured else { return }
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
        else { throw FrameSourceError.noCamera }

        captureSession.beginConfiguration()
        defer { captureSession.commitConfiguration() }
        captureSession.sessionPreset = .high

        let input: AVCaptureDeviceInput
        do {
            input = try AVCaptureDeviceInput(device: device)
        } catch {
            throw FrameSourceError.configurationFailed(error.localizedDescription)
        }
        guard captureSession.canAddInput(input) else {
            throw FrameSourceError.configurationFailed("cannot add camera input")
        }
        captureSession.addInput(input)

        output.alwaysDiscardsLateVideoFrames = true
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
        output.setSampleBufferDelegate(self, queue: bufferQueue)
        guard captureSession.canAddOutput(output) else {
            throw FrameSourceError.configurationFailed("cannot add video output")
        }
        captureSession.addOutput(output)

        // Deliver portrait buffers: the app is portrait-locked and the board is filmed top-down.
        if let connection = output.connection(with: .video),
            connection.isVideoRotationAngleSupported(90)
        {
            connection.videoRotationAngle = 90
        }
        configured = true
    }
}

extension PhoneCameraFrameSource: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(
        _ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        guard let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        lock.withLock { latestBuffer = buffer }
    }
}
