import Foundation

/// Where a take was recorded. A phone take is a development fallback and must be labelled as one
/// (IOS-08.3): it is never presented as recorded on the glasses.
enum TakeSource: String, Codable, Sendable {
    case glasses
    case phone

    var label: String {
        switch self {
        case .glasses: "Glasses camera"
        case .phone: "Phone camera (development fallback)"
        }
    }
}

/// Everything known about one take, saved next to its MP4 as `<id>.json`, so a take whose upload
/// failed survives an app restart and can be retried. The MP4 is deleted only once processing
/// has started on the server.
struct TakeRecord: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var source: TakeSource
    var recordedAt: Date
    var durationS: Double
    var stepMarksS: [Double]
    var consent: Bool
    var title: String = ""
    var chefName: String?
    /// Set once `POST /recipes` succeeded, so a retry does not create a second recipe.
    var upload: RecipeUpload?
    /// Set once `/process` answered 202.
    var processedAt: Date?

    var fileName: String { "\(id).mp4" }
}

/// `Documents/takes/`: one MP4 + one JSON per take.
struct TakeStore: Sendable {
    let directory: URL

    init(directory: URL = TakeStore.defaultDirectory) {
        self.directory = directory
    }

    static var defaultDirectory: URL {
        URL.documentsDirectory.appending(path: "takes", directoryHint: .isDirectory)
    }

    func videoURL(for id: String) -> URL { directory.appending(path: "\(id).mp4") }
    private func recordURL(for id: String) -> URL { directory.appending(path: "\(id).json") }

    func newTakeID() -> String { UUID().uuidString.lowercased() }

    func prepare() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    func save(_ record: TakeRecord) throws {
        try prepare()
        let data = try JSONCoding.encoder.encode(record)
        try data.write(to: recordURL(for: record.id), options: .atomic)
    }

    /// Takes on the phone that have not reached processing yet, newest first.
    func pending() -> [TakeRecord] {
        guard let files = try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        else { return [] }
        return files.filter { $0.pathExtension == "json" }
            .compactMap { try? JSONCoding.decoder.decode(TakeRecord.self, from: Data(contentsOf: $0)) }
            .filter { $0.processedAt == nil && FileManager.default.fileExists(atPath: videoURL(for: $0.id).path) }
            .sorted { $0.recordedAt > $1.recordedAt }
    }

    /// Removes the MP4 (and its record). Called only after `/process` succeeded, or when the
    /// chef discards a take.
    func delete(_ id: String) {
        try? FileManager.default.removeItem(at: videoURL(for: id))
        try? FileManager.default.removeItem(at: recordURL(for: id))
    }

    func fileSize(_ id: String) -> Int64? {
        (try? FileManager.default.attributesOfItem(atPath: videoURL(for: id).path)[.size] as? NSNumber)?.int64Value
    }
}
