import Foundation
import ImageIO
import UIKit

/// Step media on disk, keyed by step id (IOS-03.5). Every reference still and clip is downloaded
/// before cooking starts; the lens and "show me" read only from here, so during cooking only
/// `/check`, `/watch` and Gemini Live touch the network.
final class ImageCache: @unchecked Sendable {
    typealias Fetch = @Sendable (URL) async throws -> Data

    enum Kind: String, Sendable {
        case image = "jpg"
        case clip = "mp4"
    }

    struct Report: Equatable, Sendable {
        var downloaded = 0
        /// Downloads that failed twice; the card shows without that image or clip.
        var failed: [String] = []
        /// Failed downloads covered by a copy from an earlier session.
        var reusedFromDisk = 0
    }

    let directory: URL
    private let fetch: Fetch
    private let lock = NSLock()
    private var files: [String: URL] = [:]  // "<stepID>.<kind>" → file URL, guarded by `lock`

    init(directory: URL = ImageCache.defaultDirectory, fetch: @escaping Fetch = ImageCache.urlSessionFetch) {
        self.directory = directory
        self.fetch = fetch
    }

    static var defaultDirectory: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("StepMedia", isDirectory: true)
    }

    /// Plain GET; signed Storage URLs need no header (API-CONTRACT §1). Also reads `file://`
    /// URLs, which is how the bundled fixture's images arrive.
    static let urlSessionFetch: Fetch = { url in
        if url.isFileURL { return try Data(contentsOf: url) }
        var request = URLRequest(url: url, timeoutInterval: 15)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw URLError(.badServerResponse)
        }
        return data
    }

    /// Downloads every step's `ref_image_url` and `clip_url`. Each failed download is retried once.
    /// `progress(done, total)` is called on every finished item.
    func prefetch(
        steps: [Step], progress: @escaping @Sendable (Int, Int) -> Void = { _, _ in }
    ) async -> Report {
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let jobs: [(stepID: String, kind: Kind, url: URL)] = steps.flatMap { step in
            [
                step.refImageURL.map { (step.id, Kind.image, $0) },
                step.clipURL.map { (step.id, Kind.clip, $0) },
            ].compactMap { $0 }
        }
        progress(0, jobs.count)
        var report = Report()
        var done = 0
        await withTaskGroup(of: (String, Kind, Bool).self) { group in
            for job in jobs {
                group.addTask { [self] in
                    let ok = await download(job.url, to: fileURL(stepID: job.stepID, kind: job.kind))
                    return (job.stepID, job.kind, ok)
                }
            }
            for await (stepID, kind, ok) in group {
                done += 1
                let file = fileURL(stepID: stepID, kind: kind)
                if ok {
                    report.downloaded += 1
                    register(file, stepID: stepID, kind: kind)
                } else if FileManager.default.fileExists(atPath: file.path) {
                    report.reusedFromDisk += 1
                    register(file, stepID: stepID, kind: kind)
                } else {
                    report.failed.append("\(stepID).\(kind.rawValue)")
                }
                progress(done, jobs.count)
            }
        }
        return report
    }

    /// The cached reference still for a step, or nil when it never downloaded.
    func imageRef(stepID: String) -> ImageRef? {
        lock.withLock { files["\(stepID).\(Kind.image.rawValue)"] }.map { ImageRef(stepID: stepID, fileURL: $0) }
    }

    func clipURL(stepID: String) -> URL? {
        lock.withLock { files["\(stepID).\(Kind.clip.rawValue)"] }
    }

    func fileURL(stepID: String, kind: Kind) -> URL {
        directory.appendingPathComponent("\(stepID).\(kind.rawValue)")
    }

    private func register(_ file: URL, stepID: String, kind: Kind) {
        lock.withLock { files["\(stepID).\(kind.rawValue)"] = file }
        if kind == .image { LensImageLoader.warm(file) }
    }

    private func download(_ url: URL, to file: URL) async -> Bool {
        for attempt in 0..<2 {
            do {
                let data = try await fetch(url)
                guard !data.isEmpty else { throw URLError(.zeroByteResource) }
                try data.write(to: file, options: .atomic)
                LensImageLoader.evict(file)
                return true
            } catch is CancellationError {
                return false
            } catch {
                print("[cache] \(url.lastPathComponent) attempt \(attempt + 1) failed: \(error.localizedDescription)")
            }
        }
        return false
    }
}

/// Decoded, downsampled reference stills held in memory so a step change never decodes on the
/// main thread. Shared by every renderer that draws from `ImageRef`.
enum LensImageLoader {
    /// NSCache is thread-safe.
    nonisolated(unsafe) private static let cache = NSCache<NSURL, UIImage>()

    static func image(_ ref: ImageRef?) -> UIImage? {
        guard let url = ref?.fileURL else { return nil }
        if let hit = cache.object(forKey: url as NSURL) { return hit }
        guard let image = decode(url) else { return nil }
        cache.setObject(image, forKey: url as NSURL)
        return image
    }

    static func warm(_ url: URL) {
        if cache.object(forKey: url as NSURL) == nil, let image = decode(url) {
            cache.setObject(image, forKey: url as NSURL)
        }
    }

    static func evict(_ url: URL) {
        cache.removeObject(forKey: url as NSURL)
    }

    private static func decode(_ url: URL, maxPixels: Int = 1024) -> UIImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
            let cg = CGImageSourceCreateThumbnailAtIndex(
                source, 0,
                [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceShouldCacheImmediately: true,
                    kCGImageSourceThumbnailMaxPixelSize: maxPixels,
                ] as CFDictionary)
        else { return nil }
        return UIImage(cgImage: cg)
    }
}
