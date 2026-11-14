import CoreGraphics
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Anything that can hand over "the latest frame as a JPEG": the iPhone camera now, the glasses
/// stream in IOS-06. Everything downstream only ever sees JPEG data.
protocol FrameSource: AnyObject, Sendable {
    var isAvailable: Bool { get }
    func start() async throws
    func stop()
    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data?
}

enum FrameSourceKind: String, CaseIterable, Identifiable, Sendable {
    case phoneCamera
    case stillImage

    var id: String { rawValue }

    var label: String {
        switch self {
        case .phoneCamera: "iPhone camera"
        case .stillImage: "Still image (testing)"
        }
    }

    /// Kinds offered in Settings. The still image only appears where there is no camera.
    static var selectable: [FrameSourceKind] {
        #if targetEnvironment(simulator)
            [.phoneCamera, .stillImage]
        #else
            [.phoneCamera]
        #endif
    }
}

enum FrameSourceError: LocalizedError, Equatable {
    case permissionDenied
    case noCamera
    case configurationFailed(String)

    var errorDescription: String? {
        switch self {
        case .permissionDenied:
            "Camera access is off. Turn it on in Settings › Ghost Chef › Camera so the app can see your board."
        case .noCamera: "This device has no back camera."
        case .configurationFailed(let detail): "The camera could not start: \(detail)"
        }
    }
}

/// The two frame sizes the app sends (API-CONTRACT §3.1, §3.2).
enum FrameSpec {
    static let check = (maxLongEdge: 1280, quality: CGFloat(0.8), maxBytes: 1_500_000)
    static let watch = (maxLongEdge: 512, quality: CGFloat(0.6), maxBytes: 200_000)
}

/// Shared scaling + JPEG encoding. Thread-safe; call it off the main actor.
enum JPEGEncoder {
    /// `CIContext` is thread-safe (Apple's Core Image docs), but SDKs before iOS 26 don't mark it
    /// `Sendable`, so Swift 6.1 (Xcode 16.x) rejects a plain static. Newer SDKs at most warn here.
    nonisolated(unsafe) private static let context = CIContext(options: [.cacheIntermediates: false])

    /// Scales so the long edge is at most `maxLongEdge` (never upscales) and encodes as JPEG.
    static func encode(_ image: CIImage, maxLongEdge: Int, quality: CGFloat) -> Data? {
        let extent = image.extent.integral
        let longEdge = max(extent.width, extent.height)
        guard longEdge > 0 else { return nil }
        let scale = min(1, CGFloat(maxLongEdge) / longEdge)
        var scaled = image.transformed(by: CGAffineTransform(translationX: -extent.minX, y: -extent.minY))
        if scale < 1 {
            scaled = scaled.applyingFilter(
                "CILanczosScaleTransform",
                parameters: [kCIInputScaleKey: scale, kCIInputAspectRatioKey: 1.0])
        }
        let target = CGRect(
            x: 0, y: 0, width: floor(extent.width * scale), height: floor(extent.height * scale))
        guard let cg = context.createCGImage(scaled, from: target) else { return nil }
        return encode(cg, quality: quality)
    }

    static func encode(_ image: CGImage, quality: CGFloat) -> Data? {
        let data = NSMutableData()
        guard
            let dest = CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil)
        else { return nil }
        CGImageDestinationAddImage(
            dest, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }
        return data as Data
    }

    /// Pixel size of encoded image data, read from its header.
    static func pixelSize(of data: Data) -> CGSize? {
        guard let src = CGImageSourceCreateWithData(data as CFData, nil),
            let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
            let w = props[kCGImagePropertyPixelWidth] as? Int,
            let h = props[kCGImagePropertyPixelHeight] as? Int
        else { return nil }
        return CGSize(width: w, height: h)
    }
}
