// Renders the MockDeviceKit camera feed used on the simulator (which has no camera):
// a 6 s, 720×1280, 24 fps HEVC clip that slowly pans over a fixture reference image.
//
// Usage (from ios/):  swift scripts/make-mock-feed.swift
// Output:             GhostChef/Resources/MockFeed/mock-feed.mp4
//
// MockDeviceKit accepts h.265 (HEVC) video files as a mock camera feed (SDK 1.0.1 docs).

import AVFoundation
import CoreImage
import Foundation

let width = 720
let height = 1280
let fps: Int32 = 24
let seconds = 6
let source = URL(fileURLWithPath: "GhostChef/Resources/Fixtures/images/step-3.jpg")
let outDir = URL(fileURLWithPath: "GhostChef/Resources/MockFeed", isDirectory: true)
let output = outDir.appendingPathComponent("mock-feed.mp4")

guard let base = CIImage(contentsOf: source) else {
    FileHandle.standardError.write(Data("error: cannot read \(source.path)\n".utf8))
    exit(1)
}
try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
try? FileManager.default.removeItem(at: output)

let writer = try AVAssetWriter(outputURL: output, fileType: .mp4)
let input = AVAssetWriterInput(
    mediaType: .video,
    outputSettings: [
        AVVideoCodecKey: AVVideoCodecType.hevc,
        AVVideoWidthKey: width,
        AVVideoHeightKey: height,
        AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 1_200_000],
    ])
input.expectsMediaDataInRealTime = false
let adaptor = AVAssetWriterInputPixelBufferAdaptor(
    assetWriterInput: input,
    sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
    ])
writer.add(input)
guard writer.startWriting() else {
    FileHandle.standardError.write(Data("error: \(String(describing: writer.error))\n".utf8))
    exit(1)
}
writer.startSession(atSourceTime: .zero)

let context = CIContext()
let total = Int(fps) * seconds
// Scale the image to cover the frame with 15% headroom, then pan diagonally across it.
let cover = max(CGFloat(width) / base.extent.width, CGFloat(height) / base.extent.height) * 1.15
let scaled = base.transformed(by: CGAffineTransform(scaleX: cover, y: cover))
let slackX = scaled.extent.width - CGFloat(width)
let slackY = scaled.extent.height - CGFloat(height)

for frame in 0..<total {
    while !input.isReadyForMoreMediaData { usleep(1000) }
    let t = CGFloat(frame) / CGFloat(total - 1)
    let shifted = scaled.transformed(
        by: CGAffineTransform(translationX: -slackX * t, y: -slackY * (1 - t)))
    var buffer: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &buffer)
    guard let pixels = buffer else { exit(1) }
    context.render(
        shifted, to: pixels, bounds: CGRect(x: 0, y: 0, width: width, height: height),
        colorSpace: CGColorSpaceCreateDeviceRGB())
    adaptor.append(pixels, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: fps))
}

input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()
guard writer.status == .completed else {
    FileHandle.standardError.write(Data("error: \(String(describing: writer.error))\n".utf8))
    exit(1)
}
let size = (try? FileManager.default.attributesOfItem(atPath: output.path)[.size] as? Int) ?? 0
print("Wrote \(output.path) (\(size) bytes, \(total) frames, HEVC \(width)x\(height) @ \(fps) fps)")
