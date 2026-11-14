import Foundation

/// Turns glasses inputs into the five `CookInput`s (IOS-06.4), with the mapping in
/// `GlassesInputMapping` and the 400 ms repeat filter in `GlassesInputDebouncer`.
/// The phone's operator buttons keep working in parallel: both end in `CookSession.send`.
@MainActor
final class GlassesInputAdapter {
    private let send: @MainActor (CookInput, InputVia) -> Void
    private let now: @MainActor () -> Date
    private var debouncer = GlassesInputDebouncer()

    init(send: @escaping @MainActor (CookInput, InputVia) -> Void, now: @escaping @MainActor () -> Date = { Date() }) {
        self.send = send
        self.now = now
    }

    /// A display button on a lens card ("Check", "Next", "Dismiss").
    func handleDisplayButton(_ input: CookInput) {
        guard debouncer.accept(input, at: now()) else { return }
        send(input, .pinch)
    }

    func handle(_ kind: GlassesInputKind) {
        guard let input = GlassesInputMapping.input(for: kind), debouncer.accept(input, at: now()) else { return }
        send(input, GlassesInputMapping.via(for: kind))
    }
}
