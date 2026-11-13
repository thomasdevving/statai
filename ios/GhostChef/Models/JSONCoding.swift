import Foundation

/// The one decoder and encoder used for every API body (API-CONTRACT §1).
///
/// - Keys: `snake_case` on the wire, `camelCase` in Swift.
/// - Dates: ISO 8601, with or without fractional seconds, `Z` or a numeric offset.
/// - Free-form JSON (`payload`, `tools`) is decoded as `JSONValue`, whose object keys
///   are kept exactly as sent (no snake/camel conversion).
enum JSONCoding {
    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = ISO8601.date(from: raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container, debugDescription: "Not an ISO 8601 date: \(raw)")
            }
            return date
        }
        return d
    }()

    static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(ISO8601.string(from: date))
        }
        return e
    }()
}

/// ISO 8601 parsing that accepts what Python, Postgres and the contract examples produce:
/// `2026-11-14T09:30:00Z`, `…00.123Z`, `…00.123456+00:00`.
enum ISO8601 {
    static func date(from string: String) -> Date? {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFraction.date(from: string) { return d }

        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let d = plain.date(from: string) { return d }

        // More than 3 fractional digits (Postgres microseconds): trim to milliseconds.
        if let range = string.range(of: #"\.\d{4,}"#, options: .regularExpression) {
            let trimmed = string.replacingCharacters(
                in: range, with: String(string[range].prefix(4)))
            return withFraction.date(from: trimmed)
        }
        return nil
    }

    static func string(from date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }
}

/// A string-backed enum that decodes unknown values to a fallback case instead of throwing,
/// so a new server-side value never crashes the app (API-CONTRACT §1 "Unknown fields").
protocol LenientStringEnum: RawRepresentable, Codable, Sendable where RawValue == String {
    static var unknownCase: Self { get }
}

extension LenientStringEnum {
    init(from decoder: any Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: raw) ?? Self.unknownCase
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

extension KeyedDecodingContainer {
    /// Decodes an optional URL without failing the whole object when the string is not a valid URL.
    func decodeLenientURL(forKey key: Key) -> URL? {
        guard let raw = try? decodeIfPresent(String.self, forKey: key), !raw.isEmpty else {
            return nil
        }
        return URL(string: raw)
    }
}
