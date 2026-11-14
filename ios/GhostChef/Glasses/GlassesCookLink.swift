import Foundation
import MWDATInputs

// The SDK side of IOS-06.4: `MWDATInputs.InputEvent` → `GlassesInputKind`.
extension GlassesInputAdapter {
    /// A device event (captouch, Neural Band, buttons).
    func handle(_ event: InputEvent) {
        guard let kind = Self.kind(of: event) else { return }
        handle(kind)
    }

    nonisolated static func kind(of event: InputEvent) -> GlassesInputKind? {
        switch event {
        case .select: .select
        case .back: .back
        case .nav(let direction, _, _):
            switch direction {
            case .left: .navLeft
            case .right: .navRight
            case .up: .navUp
            case .down: .navDown
            }
        case .button: .actionButton
        case .capture: .capturePress
        case .drag: .drag
        @unknown default: nil
        }
    }
}

extension DATFrameSource {
    /// The glasses camera through `GlassesManager` (IOS-06.2).
    @MainActor
    convenience init(glasses: GlassesManager) {
        self.init(
            store: glasses.latestFrames,
            start: { [weak glasses] in await glasses?.startCookAlong() ?? false },
            stop: { [weak glasses] in await glasses?.stopCookAlong() })
    }
}

/// Runs a cook-along on the glasses: camera frames already come through `DATFrameSource`; this
/// adds the lens and the inputs, and tears both down at the end (IOS-06.3, 06.4).
@MainActor
final class GlassesCookLink {
    let renderer: GlassesLensRenderer
    let inputs: GlassesInputAdapter
    private let glasses: GlassesManager

    init(session: CookSession, glasses: GlassesManager) {
        self.glasses = glasses
        let adapter = GlassesInputAdapter { [weak session] input, via in session?.send(input, via: via) }
        inputs = adapter
        renderer = GlassesLensRenderer(session: session, glasses: glasses) { [weak adapter] input in
            adapter?.handleDisplayButton(input)
        }
    }

    func start() {
        let adapter = inputs
        glasses.onInput = { [weak adapter] event in adapter?.handle(event) }
        renderer.start()
    }

    func stop() async {
        glasses.onInput = nil
        await renderer.stop()
    }
}
