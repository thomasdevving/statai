import Foundation

// Reconnect rules (IOS-05.7), from ai/STATUS.md "Session length limit and resumption":
// - the same single-use token + the latest resumption handle reopens a session until the token's
//   `expires_at` (30 min), even past `new_session_expires_at`;
// - a new token + handle also works; a spent token without a handle is refused (1011);
// - back off 1 s, 2 s, 5 s, then give up until the next step change.

enum LiveReconnect {
    static let backoff: [Duration] = [.seconds(1), .seconds(2), .seconds(5)]

    enum Plan: Equatable {
        /// Reopen with the token we have and the handle.
        case resumeWithSameToken(handle: String)
        /// Fetch a new token; resume with the handle when there is one, else start fresh.
        case newToken(handle: String?)
    }

    /// `margin` keeps us from opening a socket with a token about to expire mid-setup.
    static func plan(token: LiveTokenResponse?, handle: String?, now: Date, margin: TimeInterval = 30) -> Plan {
        if let token, let handle, token.expiresAt.timeIntervalSince(now) > margin {
            return .resumeWithSameToken(handle: handle)
        }
        return .newToken(handle: handle)
    }

    /// Delay before attempt `n` (0-based), or `nil` once the three tries are used up.
    static func delay(beforeAttempt n: Int) -> Duration? {
        backoff.indices.contains(n) ? backoff[n] : nil
    }
}
