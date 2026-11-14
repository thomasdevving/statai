@preconcurrency import AVFoundation
import Foundation

/// Writes one take to MP4 (IOS-08.3): H.264 video from pixel buffers + AAC audio from the mic,
/// `expectsMediaDataInRealTime`, both on the host clock so they stay in sync.
///
/// Video times: arrival time on the host clock (the glasses stream has its own timestamps,
/// the mic does not share them; arrival time is the common clock, within the stream latency).
/// Audio times: the capture session's own timestamps (host clock on iOS).
/// The file starts at the first video frame; audio before it is dropped.
final class TakeWriter: @unchecked Sendable {
    enum WriterError: Error, LocalizedError, Equatable {
        case noVideo
        case failed(String)

        var errorDescription: String? {
            switch self {
            case .noVideo: "No video frames arrived, so nothing was recorded"
            case .failed(let why): "The recording could not be written: \(why)"
            }
        }
    }

    static let frameRate = 24
    static func hostNow() -> CMTime { CMClockGetTime(CMClockGetHostTimeClock()) }

    private let url: URL
    private let queue = DispatchQueue(label: "ghostchef.take.writer")
    private var writer: AVAssetWriter?
    private var videoInput: AVAssetWriterInput?
    private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
    private var audioInput: AVAssetWriterInput?
    private var sessionStart: CMTime?
    private var lastVideoTime: CMTime?
    private var lastAudioEnd: CMTime?
    private var size: (width: Int, height: Int) = (0, 0)
    private var frames = 0
    private var audioBuffers = 0
    private var dropped = 0
    private var failure: String?
    private var finished = false

    init(url: URL) {
        self.url = url
        try? FileManager.default.removeItem(at: url)
    }

    // MARK: Append (any thread)

    func appendVideo(_ pixels: CVPixelBuffer, at time: CMTime) {
        nonisolated(unsafe) let pixels = pixels
        queue.async { self.writeVideo(pixels, at: time) }
    }

    func appendAudio(_ sample: CMSampleBuffer) {
        nonisolated(unsafe) let sample = sample
        queue.async { self.writeAudio(sample) }
    }

    // MARK: Finish

    /// Closes the file. Returns its duration and what went into it.
    func finish() async throws -> TakeCaptureResult {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<TakeCaptureResult, any Error>) in
            queue.async {
                guard let writer = self.writer, let start = self.sessionStart, let last = self.lastVideoTime else {
                    self.finished = true
                    cont.resume(throwing: WriterError.noVideo)
                    return
                }
                if let failure = self.failure {
                    writer.cancelWriting()
                    self.finished = true
                    cont.resume(throwing: WriterError.failed(failure))
                    return
                }
                self.finished = true
                // The last frame lasts one frame period; audio may run slightly past it.
                var end = CMTimeAdd(last, CMTime(value: 1, timescale: CMTimeScale(Self.frameRate)))
                if let audioEnd = self.lastAudioEnd, audioEnd > end { end = audioEnd }
                writer.endSession(atSourceTime: end)
                self.videoInput?.markAsFinished()
                self.audioInput?.markAsFinished()
                let result = TakeCaptureResult(
                    durationS: CMTimeSubtract(end, start).seconds, width: self.size.width, height: self.size.height,
                    videoFrames: self.frames, hasAudio: self.audioBuffers > 0)
                writer.finishWriting {
                    if writer.status == .completed {
                        cont.resume(returning: result)
                    } else {
                        cont.resume(throwing: WriterError.failed(writer.error?.localizedDescription ?? "status \(writer.status.rawValue)"))
                    }
                }
            }
        }
    }

    // MARK: Writing (queue only)

    private func writeVideo(_ pixels: CVPixelBuffer, at time: CMTime) {
        guard !finished, failure == nil else { return }
        if writer == nil { begin(width: CVPixelBufferGetWidth(pixels), height: CVPixelBufferGetHeight(pixels), at: time) }
        guard let adaptor, let videoInput, failure == nil else { return }
        if let lastVideoTime, time <= lastVideoTime { return }  // timestamps must increase
        guard videoInput.isReadyForMoreMediaData else {
            dropped += 1
            return
        }
        if adaptor.append(pixels, withPresentationTime: time) {
            frames += 1
            lastVideoTime = time
        } else {
            failure = writer?.error?.localizedDescription ?? "video append failed"
        }
    }

    private func writeAudio(_ sample: CMSampleBuffer) {
        guard !finished, failure == nil, let audioInput, let sessionStart else { return }
        let time = CMSampleBufferGetPresentationTimeStamp(sample)
        guard time >= sessionStart, audioInput.isReadyForMoreMediaData else { return }
        if audioInput.append(sample) {
            audioBuffers += 1
            lastAudioEnd = CMTimeAdd(time, CMSampleBufferGetDuration(sample))
        }
    }

    private func begin(width: Int, height: Int, at time: CMTime) {
        do {
            let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
            let video = AVAssetWriterInput(
                mediaType: .video,
                outputSettings: [
                    AVVideoCodecKey: AVVideoCodecType.h264,
                    AVVideoWidthKey: width,
                    AVVideoHeightKey: height,
                    AVVideoCompressionPropertiesKey: [
                        AVVideoAverageBitRateKey: Self.bitRate(width: width, height: height),
                        AVVideoExpectedSourceFrameRateKey: Self.frameRate,
                        AVVideoMaxKeyFrameIntervalKey: Self.frameRate * 2,
                    ],
                ])
            video.expectsMediaDataInRealTime = true
            let audio = AVAssetWriterInput(
                mediaType: .audio,
                outputSettings: [
                    AVFormatIDKey: kAudioFormatMPEG4AAC,
                    AVNumberOfChannelsKey: 1,
                    AVSampleRateKey: 44_100,
                    AVEncoderBitRateKey: 96_000,
                ])
            audio.expectsMediaDataInRealTime = true
            guard writer.canAdd(video), writer.canAdd(audio) else {
                failure = "the writer refused the video or audio track"
                return
            }
            writer.add(video)
            writer.add(audio)
            let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: video, sourcePixelBufferAttributes: nil)
            guard writer.startWriting() else {
                failure = writer.error?.localizedDescription ?? "startWriting failed"
                return
            }
            writer.startSession(atSourceTime: time)
            self.writer = writer
            videoInput = video
            audioInput = audio
            self.adaptor = adaptor
            sessionStart = time
            size = (width, height)
        } catch {
            failure = error.localizedDescription
        }
    }

    /// ~6 Mbit/s at 720×1280, scaled by pixel count (enough for Gemini to read hands and food).
    static func bitRate(width: Int, height: Int) -> Int {
        max(1_500_000, Int(Double(width * height) / Double(720 * 1280) * 6_000_000))
    }
}

/// The microphone as CMSampleBuffers for `TakeWriter` (IOS-08.3). Uses whatever input the audio
/// session routes to (the glasses' mic over Bluetooth if that route is active; IOS-02 proof f
/// has not decided it yet).
final class MicCapture: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate, @unchecked Sendable {
    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "ghostchef.take.mic")
    private let onSample: @Sendable (CMSampleBuffer) -> Void

    init(onSample: @escaping @Sendable (CMSampleBuffer) -> Void) {
        self.onSample = onSample
    }

    enum MicError: Error, LocalizedError {
        case denied, noMicrophone, configuration

        var errorDescription: String? {
            switch self {
            case .denied: "Microphone access was refused. Allow it in Settings to record the chef's voice."
            case .noMicrophone: "No microphone is available"
            case .configuration: "The microphone could not be set up"
            }
        }
    }

    func start() async throws {
        guard await AVCaptureDevice.requestAccess(for: .audio) else { throw MicError.denied }
        guard let device = AVCaptureDevice.default(for: .audio) else { throw MicError.noMicrophone }
        let input = try AVCaptureDeviceInput(device: device)
        session.beginConfiguration()
        guard session.canAddInput(input), session.canAddOutput(output) else {
            session.commitConfiguration()
            throw MicError.configuration
        }
        session.addInput(input)
        output.setSampleBufferDelegate(self, queue: queue)
        session.addOutput(output)
        session.commitConfiguration()
        let session = session
        await withCheckedContinuation { cont in
            queue.async {
                session.startRunning()
                cont.resume()
            }
        }
    }

    func stop() {
        let session = session
        queue.async { if session.isRunning { session.stopRunning() } }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        onSample(sampleBuffer)
    }
}
