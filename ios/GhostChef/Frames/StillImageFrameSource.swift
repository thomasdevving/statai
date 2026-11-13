import CoreImage
import Foundation
import UIKit

/// A `FrameSource` that always returns the same image. For unit tests and the simulator.
final class StillImageFrameSource: FrameSource, @unchecked Sendable {
    private let image: CIImage

    init(image: CIImage) {
        self.image = image
    }

    convenience init?(jpeg: Data) {
        guard let image = CIImage(data: jpeg) else { return nil }
        self.init(image: image)
    }

    var isAvailable: Bool { true }
    func start() async throws {}
    func stop() {}

    func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? {
        JPEGEncoder.encode(image, maxLongEdge: maxLongEdge, quality: quality)
    }

    /// A 1080×1920 portrait test card with enough detail that its JPEG is not trivially small.
    static func testCard() -> StillImageFrameSource {
        let size = CGSize(width: 1080, height: 1920)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let rendered = UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            let cg = ctx.cgContext
            // Board.
            UIColor(red: 0.62, green: 0.46, blue: 0.30, alpha: 1).setFill()
            cg.fill(CGRect(origin: .zero, size: size))
            // Wood grain so the encoder has real detail to work with.
            for i in 0..<240 {
                let y = CGFloat(i) * 8
                UIColor(white: 0, alpha: CGFloat((i * 37) % 11) / 60).setStroke()
                cg.setLineWidth(CGFloat((i * 13) % 5 + 1))
                cg.move(to: CGPoint(x: 0, y: y))
                cg.addCurve(
                    to: CGPoint(x: size.width, y: y + CGFloat((i * 7) % 30)),
                    control1: CGPoint(x: 300, y: y - 20), control2: CGPoint(x: 700, y: y + 25))
                cg.strokePath()
            }
            // Nori sheet with rice.
            let nori = CGRect(x: 140, y: 560, width: 800, height: 720)
            UIColor(red: 0.08, green: 0.14, blue: 0.08, alpha: 1).setFill()
            cg.fill(nori)
            UIColor(white: 0.96, alpha: 1).setFill()
            for i in 0..<900 {
                let x = nori.minX + CGFloat((i * 97) % 800)
                let y = nori.minY + 60 + CGFloat((i * 53) % 660)
                cg.fillEllipse(in: CGRect(x: x, y: y, width: 14, height: 9))
            }
            let label = "STILL TEST IMAGE — not a camera frame" as NSString
            label.draw(
                at: CGPoint(x: 60, y: 120),
                withAttributes: [
                    .font: UIFont.systemFont(ofSize: 44, weight: .bold), .foregroundColor: UIColor.white,
                ])
        }
        return StillImageFrameSource(image: CIImage(cgImage: rendered.cgImage!))
    }
}
