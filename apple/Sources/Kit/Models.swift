import Foundation

// The shapes the Amin server sends (amin/api.py). Value types throughout:
// nothing here has identity beyond its id.

nonisolated struct Prefs: Codable, Hashable, Sendable {
  var chatPrivate: Bool
  var chatHousehold: Bool
}

nonisolated struct Project: Codable, Hashable, Identifiable, Sendable {
  let id: String
  var name: String
  let owner: String
  var members: [String]
  var grantPrivate: Bool
  var grantHousehold: Bool
  var generalChat: Bool
  let role: String          // "owner" | "member"
  var documents: [String]

  var isOwner: Bool { role == "owner" }
}

nonisolated struct Me: Codable, Hashable, Sendable {
  let name: String
  let admin: Bool
  let people: [String]
  var prefs: Prefs
  var `private`: [String]
  var household: [String]
  var projects: [Project]
}

nonisolated struct Claim: Codable, Hashable, Sendable {
  let text: String
  let citations: [String]
  let verdict: String
}

nonisolated struct SourceRef: Codable, Hashable, Sendable {
  let docId: String
  let heading: String
}

/// One answer. `basis` is "documents" or "general"; a refusal or a routed
/// question has no claims and a `refusalReason`.
nonisolated struct Answer: Codable, Hashable, Sendable {
  let question: String
  var askedAs: String? = nil
  let outcome: String
  let basis: String
  var routedTo: String? = nil
  var refusalReason: String? = nil
  let claims: [Claim]
  var sources: [String: SourceRef]? = nil
  let latencyMs: Int
  var conversationId: String? = nil
  var factId: String? = nil

  var isRemembered: Bool { outcome == "remembered" }

  var text: String {
    let t = claims.map(\.text).joined(separator: " ")
    return t.isEmpty ? (refusalReason ?? "") : t
  }
  var isGeneral: Bool { basis == "general" }
  var isConflict: Bool { outcome == "conflict" }

  /// Cited chunk ids in order of first appearance: the numbers 1, 2, 3 the reader sees.
  var citationOrder: [String] {
    var seen: [String] = []
    for id in claims.flatMap(\.citations) where !seen.contains(id) { seen.append(id) }
    return seen
  }
}

nonisolated struct ConversationSummary: Codable, Hashable, Identifiable, Sendable {
  let id: String
  let title: String
  let project: String?
  let updated: Double
}

nonisolated struct Exchange: Codable, Hashable, Sendable {
  let question: String
  let answer: Answer
}

nonisolated struct Conversation: Codable, Hashable, Sendable {
  let id: String
  let title: String
  let project: String?
  let messages: [Exchange]
}

nonisolated struct Chunk: Codable, Hashable, Sendable {
  let docId: String
  let heading: String
  let text: String

  /// "h.lease.pdf" → ("Household", "lease.pdf"); doc ids carry their library.
  var library: (name: String, file: String) {
    if docId.hasPrefix("h.") { return ("Household", String(docId.dropFirst(2))) }
    if docId.hasPrefix("p.") { return ("Only me", String(docId.dropFirst(2))) }
    if docId.hasPrefix("j."), let dot = docId.dropFirst(2).firstIndex(of: ".") {
      return ("Project", String(docId[docId.index(after: dot)...]))
    }
    return ("Library", docId)
  }
}

/// Something the person taught Amin ("remember that …"): their memory (ADR-015).
nonisolated struct Fact: Codable, Hashable, Identifiable, Sendable {
  let id: String
  let text: String
  let created: Double
}

nonisolated struct Transcript: Codable, Hashable, Sendable {
  let text: String
  let lang: String
}

/// Where a document is saved.
nonisolated enum Library: Hashable, Sendable {
  case mine, household, project(String)
}

nonisolated enum AminError: LocalizedError, Equatable {
  case notSignedIn
  case server(String)
  case unreachable(String)

  var errorDescription: String? {
    switch self {
    case .notSignedIn: "Sign in to Amin first."
    case .server(let message): message
    case .unreachable(let host): "Can't reach Amin at \(host). Is the Amin computer on, and on the same network?"
    }
  }
}

/// One of Amin's own models, as the Amin computer offers it for download (/models).
nonisolated struct ModelInfo: Codable, Hashable, Identifiable, Sendable {
  struct File: Codable, Hashable, Sendable { let name: String; let bytes: Int64 }
  let name: String
  let purpose: String
  let bytes: Int64
  let files: [File]
  var id: String { name }
}
