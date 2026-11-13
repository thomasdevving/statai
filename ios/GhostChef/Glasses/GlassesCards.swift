// Display DSL builders for the glasses lens. Kept free of SwiftUI on purpose: MWDATDisplay's
// `Text`, `Image` and `Button` would otherwise clash with SwiftUI's (SDK 1.0.1 display guide).

import Foundation
import MWDATDisplay
import UIKit

enum GlassesCards {
    /// IOS-02 proof c: the step card from the TECH-SPEC display spec: step number + title,
    /// the chef's reference still, and the key line. Bright on black; black is transparent.
    static func stepCard(
        index: Int, total: Int, title: String, keyLine: String, image: UIImage?, footer: String? = nil
    ) -> FlexBox {
        // The image takes only the space the text leaves: with `.fill` and no shrink it pushed
        // the key line off the card (seen in the MockDeviceKit preview, 2026-11-14).
        FlexBox(direction: .column, spacing: 8) {
            Text("\(index)/\(total)  \(title)", style: .heading)
                .flexShrink(0)
            if let image {
                Image(image: image, sizePreset: .fill, cornerRadius: .small)
                    .flexShrink(1)
            }
            Text(keyLine, style: .body)
                .flexShrink(0)
            if let footer {
                Text(footer, style: .meta, color: .secondary)
                    .flexShrink(0)
            }
        }
        .padding(16)
    }

    /// IOS-02 proof e: two display buttons whose clicks are logged, next to whatever
    /// device inputs (captouch, Neural Band, buttons) arrive through MWDATInputs.
    static func inputCard(
        onCheck: @escaping @Sendable () -> Void, onNext: @escaping @Sendable () -> Void
    ) -> FlexBox {
        FlexBox(direction: .column, spacing: 12) {
            Text("Input test", style: .heading)
            Text("Press a button, pinch, swipe or tap", style: .body, color: .secondary)
            ButtonGroup {
                Button(label: "Check", style: .primary, iconName: .checkmark, onClick: onCheck)
                    .actionRole(.primary)
                Button(label: "Next", style: .secondary, onClick: onNext)
            }
        }
        .padding(16)
    }

    /// Small enough for the lens, decoded without inflating the full image, and center-cropped
    /// to `aspect` (width / height). A `.fill` image spans the card's width, so a portrait
    /// 720×1280 still would be taller than the card and push the key line off it; a 16:10
    /// crop leaves room for both text lines (checked in the MockDeviceKit preview).
    static func loadThumbnail(_ url: URL?, maxPixels: Int = 640, aspect: CGFloat = 16 / 10) -> UIImage? {
        guard let url, let source = CGImageSourceCreateWithURL(url as CFURL, nil),
            let cg = CGImageSourceCreateThumbnailAtIndex(
                source, 0,
                [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceThumbnailMaxPixelSize: maxPixels,
                ] as CFDictionary)
        else { return nil }
        let w = CGFloat(cg.width)
        let h = CGFloat(cg.height)
        let crop: CGRect =
            w / h > aspect
            ? CGRect(x: (w - h * aspect) / 2, y: 0, width: h * aspect, height: h)
            : CGRect(x: 0, y: (h - w / aspect) / 2, width: w, height: w / aspect)
        return UIImage(cgImage: cg.cropping(to: crop.integral) ?? cg)
    }
}
