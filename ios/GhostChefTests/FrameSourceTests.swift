import CoreImage
import Foundation
import Testing

@testable import GhostChef

@Suite("Frame encoding")
struct FrameSourceTests {
    @Test(arguments: [
        ("check", FrameSpec.check.maxLongEdge, FrameSpec.check.quality, FrameSpec.check.maxBytes),
        ("watch", FrameSpec.watch.maxLongEdge, FrameSpec.watch.quality, FrameSpec.watch.maxBytes),
    ])
    func stillImageMeetsContractLimits(name: String, maxLongEdge: Int, quality: CGFloat, maxBytes: Int) async throws {
        let source = StillImageFrameSource.testCard()
        let data = try #require(await source.latestJPEG(maxLongEdge: maxLongEdge, quality: quality))
        let size = try #require(JPEGEncoder.pixelSize(of: data))
        #expect(Int(max(size.width, size.height)) == maxLongEdge, "\(name): long edge")
        #expect(size.height > size.width, "\(name): portrait")
        #expect(data.count <= maxBytes, "\(name): \(data.count) bytes")
        // The fake AI treats < 5000 bytes as unjudgeable; a real frame must be bigger.
        #expect(data.count > 5000, "\(name): \(data.count) bytes")
        #expect(data.starts(with: [0xFF, 0xD8]), "\(name): JPEG magic")
    }

    @Test func neverUpscales() throws {
        let small = CIImage(color: .red).cropped(to: CGRect(x: 0, y: 0, width: 300, height: 400))
        let data = try #require(JPEGEncoder.encode(small, maxLongEdge: 1280, quality: 0.8))
        #expect(JPEGEncoder.pixelSize(of: data) == CGSize(width: 300, height: 400))
    }

    @Test func multipartBody() {
        var form = MultipartFormData(boundary: "B")
        form.addField(name: "a", value: "1")
        let body = String(decoding: form.finalized(), as: UTF8.self)
        #expect(body == "--B\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n1\r\n--B--\r\n")
        #expect(form.contentType == "multipart/form-data; boundary=B")
    }
}
