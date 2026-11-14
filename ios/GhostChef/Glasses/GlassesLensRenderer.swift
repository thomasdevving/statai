import Foundation
import MWDATDisplay
import Observation
import UIKit

/// Draws `CookSession.lens` on the glasses display (IOS-06.3). The phone preview and the lens
/// render the same `LensScreen`, so they always show the same state.
///
/// - Sends only on change, at most about twice a second (`GlassesDisplayThrottle`).
/// - Reference images are pre-scaled and cached per step.
/// - Clears the display when stopped. A display error never crashes: after three failures in a
///   row it stops sending and the audio path carries on (IOS-07 owns the audio-only mode).
@MainActor
final class GlassesLensRenderer {
    private let session: CookSession
    private let glasses: GlassesManager
    private let onInput: @MainActor (CookInput) -> Void
    private var throttle = GlassesDisplayThrottle()
    private var thumbnails: [String: UIImage] = [:]
    private var pending: Task<Void, Never>?
    private var running = false
    private var failures = 0
    private(set) var gaveUp = false

    static let maxFailures = 3

    init(session: CookSession, glasses: GlassesManager, onInput: @escaping @MainActor (CookInput) -> Void) {
        self.session = session
        self.glasses = glasses
        self.onInput = onInput
    }

    func start() {
        guard !running else { return }
        running = true
        gaveUp = false
        failures = 0
        throttle.reset()
        observe()
    }

    func stop() async {
        running = false
        // Let a send already on the wire finish first, or it could land after the clear and
        // leave a stale card on the lens.
        let inFlight = pending
        pending = nil
        inFlight?.cancel()
        await inFlight?.value
        throttle.reset()
        await glasses.clearLens()
    }

    /// Re-arms observation of `session.lens` after every change.
    private func observe() {
        guard running else { return }
        let screen = withObservationTracking {
            // Also redraw when the display (re)starts, e.g. it came up after the session did.
            _ = glasses.displayState
            return session.lens
        } onChange: { [weak self] in
            Task { @MainActor in self?.observe() }
        }
        render(screen)
    }

    private func render(_ screen: LensScreen) {
        guard running, !gaveUp, glasses.canDisplay else { return }
        let spec = GlassesLensLayout.card(for: screen)
        switch throttle.plan(for: spec, now: .now) {
        case .skip:
            return
        case .sendNow:
            pending?.cancel()
            pending = Task { await self.send(spec) }
        case .sendAfter(let delay):
            // Coalesce: when the timer fires, draw whatever the lens shows then.
            pending?.cancel()
            pending = Task {
                try? await Task.sleep(for: .seconds(delay))
                guard !Task.isCancelled else { return }
                let latest = GlassesLensLayout.card(for: self.session.lens)
                if self.throttle.plan(for: latest, now: .now) != .skip { await self.send(latest) }
            }
        }
    }

    private func send(_ spec: GlassesCardSpec?) async {
        guard running else { return }
        throttle.didSend(spec, at: .now)
        do {
            if let spec {
                let onInput = onInput
                let view = GlassesCards.card(spec, image: thumbnail(spec.image)) { input in
                    Task { @MainActor in onInput(input) }
                }
                try await glasses.showOnLens(view)
            } else {
                await glasses.clearLens()
            }
            failures = 0
        } catch {
            // Not sent: forget it so the same card is tried again on the next change.
            throttle.reset()
            failures += 1
            glasses.note("Lens send failed (\(failures)): \(error.localizedDescription)")
            if failures >= Self.maxFailures {
                gaveUp = true
                glasses.note("Lens: giving up after \(failures) failures; audio carries on")
            }
        }
    }

    private func thumbnail(_ ref: ImageRef?) -> UIImage? {
        guard let ref else { return nil }
        if let cached = thumbnails[ref.stepID] { return cached }
        let image = GlassesCards.loadThumbnail(ref.fileURL)
        thumbnails[ref.stepID] = image
        return image
    }
}
