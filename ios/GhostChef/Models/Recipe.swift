import Foundation

// API-CONTRACT §2: recipes and steps.
// IDs are kept as strings: the contract says UUID v4, but comparing strings avoids case
// mismatches between what the server echoes and what Swift's UUID prints.

enum RecipeStatus: String, LenientStringEnum, CaseIterable {
    case uploading, processing, review, published, failed, unknown
    static var unknownCase: Self { .unknown }
}

struct WatchFor: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var mistake: String
    var headline: String
    var fix: String
    var spoken: String
}

struct Step: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var recipeID: String
    var idx: Int
    var title: String
    var keyLine: String
    var instruction: String
    var chefQuote: String?
    var timestampS: Double
    var clipStartS: Double?
    var clipEndS: Double?
    var successCriteria: [String]
    var watchFors: [WatchFor]
    var refImageURL: URL?
    var clipURL: URL?
    var timerS: Int?

    // Names are what `convertFromSnakeCase` produces from the wire keys.
    enum CodingKeys: String, CodingKey {
        case id, idx, title, keyLine, instruction, chefQuote, timestampS, clipStartS, clipEndS
        case successCriteria, watchFors, timerS
        case recipeID = "recipeId"
        case refImageURL = "refImageUrl"
        case clipURL = "clipUrl"
    }

    init(
        id: String, recipeID: String, idx: Int, title: String, keyLine: String,
        instruction: String, chefQuote: String? = nil, timestampS: Double,
        clipStartS: Double? = nil, clipEndS: Double? = nil, successCriteria: [String] = [],
        watchFors: [WatchFor] = [], refImageURL: URL? = nil, clipURL: URL? = nil,
        timerS: Int? = nil
    ) {
        self.id = id
        self.recipeID = recipeID
        self.idx = idx
        self.title = title
        self.keyLine = keyLine
        self.instruction = instruction
        self.chefQuote = chefQuote
        self.timestampS = timestampS
        self.clipStartS = clipStartS
        self.clipEndS = clipEndS
        self.successCriteria = successCriteria
        self.watchFors = watchFors
        self.refImageURL = refImageURL
        self.clipURL = clipURL
        self.timerS = timerS
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        recipeID = try c.decode(String.self, forKey: .recipeID)
        idx = try c.decode(Int.self, forKey: .idx)
        title = try c.decode(String.self, forKey: .title)
        keyLine = try c.decode(String.self, forKey: .keyLine)
        instruction = try c.decodeIfPresent(String.self, forKey: .instruction) ?? ""
        chefQuote = try c.decodeIfPresent(String.self, forKey: .chefQuote)
        timestampS = try c.decode(Double.self, forKey: .timestampS)
        clipStartS = try c.decodeIfPresent(Double.self, forKey: .clipStartS)
        clipEndS = try c.decodeIfPresent(Double.self, forKey: .clipEndS)
        successCriteria = try c.decodeIfPresent([String].self, forKey: .successCriteria) ?? []
        watchFors = try c.decodeIfPresent([WatchFor].self, forKey: .watchFors) ?? []
        refImageURL = c.decodeLenientURL(forKey: .refImageURL)
        clipURL = c.decodeLenientURL(forKey: .clipURL)
        timerS = try c.decodeIfPresent(Int.self, forKey: .timerS)
    }
}

/// One row of `GET /recipes`.
struct RecipeSummary: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var title: String
    var chefName: String?
    var status: RecipeStatus
    var stepCount: Int
    var createdAt: Date?
}

struct RecipeList: Codable, Sendable, Equatable {
    var recipes: [RecipeSummary]
}

/// `GET /recipes/{id}`.
struct Recipe: Codable, Sendable, Hashable, Identifiable {
    var id: String
    var title: String
    var chefName: String?
    var status: RecipeStatus
    var error: String?
    var videoURL: URL?
    /// Seconds at which the chef pinched "new step" while recording (contract v2.0). Hints only.
    var stepMarksS: [Double]
    var transcript: String?
    var createdAt: Date?
    var steps: [Step]

    enum CodingKeys: String, CodingKey {
        case id, title, chefName, status, error, stepMarksS, transcript, createdAt, steps
        case videoURL = "videoUrl"
    }

    init(
        id: String, title: String, chefName: String? = nil, status: RecipeStatus,
        error: String? = nil, videoURL: URL? = nil, stepMarksS: [Double] = [],
        transcript: String? = nil, createdAt: Date? = nil, steps: [Step]
    ) {
        self.id = id
        self.title = title
        self.chefName = chefName
        self.status = status
        self.error = error
        self.videoURL = videoURL
        self.stepMarksS = stepMarksS
        self.transcript = transcript
        self.createdAt = createdAt
        self.steps = steps
    }

    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        chefName = try c.decodeIfPresent(String.self, forKey: .chefName)
        status = try c.decode(RecipeStatus.self, forKey: .status)
        error = try c.decodeIfPresent(String.self, forKey: .error)
        videoURL = c.decodeLenientURL(forKey: .videoURL)
        stepMarksS = try c.decodeIfPresent([Double].self, forKey: .stepMarksS) ?? []
        transcript = try c.decodeIfPresent(String.self, forKey: .transcript)
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt)
        steps = (try c.decodeIfPresent([Step].self, forKey: .steps) ?? []).sorted { $0.idx < $1.idx }
    }

    var summary: RecipeSummary {
        RecipeSummary(
            id: id, title: title, chefName: chefName, status: status, stepCount: steps.count,
            createdAt: createdAt)
    }
}
