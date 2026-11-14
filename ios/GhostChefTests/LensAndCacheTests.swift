import Foundation
import Testing

@testable import GhostChef

@Suite("LensScreen spoken forms")
struct LensSpokenTests {
    let card = StepCard(
        idx: 3, total: 8, title: "Spread rice", keyLine: "Thin layer, leave 2cm top", refImage: nil,
        watching: .active)

    @Test func everyCase() {
        #expect(LensScreen.step(card).spokenText == "Step 3 of 8. Spread rice. Thin layer, leave 2cm top.")
        #expect(LensScreen.checking(card).spokenText == "Checking.")
        #expect(LensScreen.pass(headline: "Looks right").spokenText == "Looks right.")
        #expect(
            LensScreen.fix(card, headline: "Too much rice", fix: "Spread thinner, 2cm nori free", proactive: true)
                .spokenText == "Too much rice. Spread thinner, 2cm nori free.")
        #expect(
            LensScreen.unsure(headline: "Can't tell", hint: "Look straight down at mat").spokenText
                == "Can't tell. Look straight down at mat.")
        #expect(LensScreen.unsure(headline: "Can't tell", hint: "").spokenText == "Can't tell.")
        #expect(LensScreen.talking(phase: .listening, caption: "").spokenText == nil)
        #expect(LensScreen.talking(phase: .answering, caption: "Use less rice").spokenText == nil)
        #expect(LensScreen.showMe(card).spokenText == "Here is how the chef did it.")
        #expect(LensScreen.timer(remainingS: 200, card).spokenText == "3 minutes 20 seconds left.")
        #expect(LensScreen.timer(remainingS: 60, card).spokenText == "1 minute left.")
        #expect(LensScreen.timer(remainingS: 1, card).spokenText == "1 second left.")
        #expect(
            LensScreen.done(SessionSummary(stepsTotal: 8, stepsPassedFirstTry: 6, fixesCaught: 1, warnings: 0, questions: 0))
                .spokenText == "Done. 6 of 8 steps right first time, 1 fix caught.")
        #expect(LensScreen.done(nil).spokenText == "Done. Well cooked.")
        #expect(LensScreen.notice("No connection").spokenText == "No connection.")
        #expect(LensScreen.recipePick(titles: ["Maki roll", "Onigiri"], selected: 1).spokenText == "Recipe 2 of 2: Onigiri.")
        #expect(LensScreen.recipePick(titles: [], selected: 0).spokenText == "No recipes yet.")
    }

    @Test func sentenceKeepsExistingPunctuation() {
        #expect(LensScreen.sentence("Looks right!") == "Looks right!")
        #expect(LensScreen.sentence("  Roll  ") == "Roll.")
        #expect(LensScreen.sentence("") == "")
    }

    @Test func cardAccessor() {
        #expect(LensScreen.step(card).card == card)
        #expect(LensScreen.fix(card, headline: "", fix: "", proactive: false).card == card)
        #expect(LensScreen.pass(headline: "x").card == nil)
    }
}

@Suite("ImageCache")
struct ImageCacheTests {
    private func dir() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("ImageCacheTests-\(UUID().uuidString)")
    }

    private func steps(_ n: Int, clips: Bool = false) -> [Step] {
        (1...n).map { i in
            Step(
                id: "step-\(i)", recipeID: "r", idx: i, title: "T\(i)", keyLine: "K\(i)", instruction: "",
                timestampS: 0, refImageURL: URL(string: "https://example.invalid/\(i).jpg"),
                clipURL: clips ? URL(string: "https://example.invalid/\(i).mp4") : nil)
        }
    }

    @Test func downloadsEveryImageAndClipToDisk() async throws {
        let cache = ImageCache(directory: dir()) { url in Data(url.lastPathComponent.utf8) }
        let progress = ProgressLog()
        let report = await cache.prefetch(steps: steps(3, clips: true)) { done, total in progress.add(done, total) }
        #expect(report.downloaded == 6)
        #expect(report.failed.isEmpty)
        for i in 1...3 {
            let ref = try #require(cache.imageRef(stepID: "step-\(i)"))
            #expect(try Data(contentsOf: ref.fileURL) == Data("\(i).jpg".utf8))
            let clip = try #require(cache.clipURL(stepID: "step-\(i)"))
            #expect(try Data(contentsOf: clip) == Data("\(i).mp4".utf8))
        }
        #expect(progress.entries.first?.0 == 0)
        #expect(progress.entries.last.map { $0 == (6, 6) } == true)
    }

    @Test func failedDownloadIsRetriedOnceThenCardHasNoImage() async throws {
        let attempts = AttemptCounter()
        let cache = ImageCache(directory: dir()) { url in
            let n = attempts.increment(url.lastPathComponent)
            if url.lastPathComponent == "2.jpg" { throw URLError(.notConnectedToInternet) }
            if url.lastPathComponent == "3.jpg", n == 1 { throw URLError(.timedOut) }  // succeeds on retry
            return Data("ok".utf8)
        }
        let report = await cache.prefetch(steps: steps(3))
        #expect(attempts.count("2.jpg") == 2)
        #expect(attempts.count("3.jpg") == 2)
        #expect(attempts.count("1.jpg") == 1)
        #expect(report.failed == ["step-2.jpg"])
        #expect(cache.imageRef(stepID: "step-2") == nil)
        #expect(cache.imageRef(stepID: "step-3") != nil)
    }

    @Test func offlineRestartReusesTheCopyFromAnEarlierSession() async throws {
        let directory = dir()
        _ = await ImageCache(directory: directory) { _ in Data("old".utf8) }.prefetch(steps: steps(1))
        let offline = ImageCache(directory: directory) { _ in throw URLError(.notConnectedToInternet) }
        let report = await offline.prefetch(steps: steps(1))
        #expect(report.reusedFromDisk == 1)
        #expect(report.failed.isEmpty)
        let ref = try #require(offline.imageRef(stepID: "step-1"))
        #expect(try Data(contentsOf: ref.fileURL) == Data("old".utf8))
    }

    @Test func bundledFixtureImagesCopyThroughFileURLs() async throws {
        let recipe = try FixtureRecipe.load()
        let cache = ImageCache(directory: dir())
        let report = await cache.prefetch(steps: recipe.steps)
        #expect(report.downloaded == recipe.steps.count)
        for step in recipe.steps {
            let ref = try #require(cache.imageRef(stepID: step.id))
            #expect(LensImageLoader.image(ref) != nil)
        }
    }
}

@Suite("Chime")
struct ChimeTests {
    @Test func isAValidWAV() {
        let wav = Chime.wav
        #expect(wav.prefix(4) == Data("RIFF".utf8))
        #expect(wav.count > 30_000)
    }
}

final class ProgressLog: @unchecked Sendable {
    private let lock = NSLock()
    private var _entries: [(Int, Int)] = []
    func add(_ done: Int, _ total: Int) { lock.withLock { _entries.append((done, total)) } }
    var entries: [(Int, Int)] { lock.withLock { _entries } }
}

final class AttemptCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var counts: [String: Int] = [:]
    func increment(_ key: String) -> Int {
        lock.withLock {
            counts[key, default: 0] += 1
            return counts[key]!
        }
    }
    func count(_ key: String) -> Int { lock.withLock { counts[key] ?? 0 } }
}
