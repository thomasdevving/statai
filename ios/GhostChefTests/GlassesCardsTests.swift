import Foundation
import Testing

@testable import GhostChef

@Suite("Glasses cards")
struct GlassesCardsTests {
    /// The lens card spans the display width, so the reference still must be landscape or the
    /// key line is pushed off the card (seen in the MockDeviceKit preview).
    @Test func referenceStillIsCroppedToLandscape() throws {
        let step = try #require(try FixtureRecipe.load().steps.first { $0.idx == 3 })
        let image = try #require(GlassesCards.loadThumbnail(step.refImageURL))
        let ratio = image.size.width / image.size.height
        #expect(abs(ratio - 16.0 / 10.0) < 0.02, "ratio \(ratio)")
        #expect(max(image.size.width, image.size.height) <= 640)
    }

    @Test func missingImageIsNil() {
        #expect(GlassesCards.loadThumbnail(nil) == nil)
    }
}
