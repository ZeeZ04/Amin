import Foundation

/// Where answers come from. Today: an Amin server on the home network. The
/// on-device engine (Gemma 4 E4B through MLX Swift, ADR-014) will conform to
/// the same protocol, so no view changes when it lands.
nonisolated protocol Engine: Sendable {
  func ask(_ question: String, project: String?, conversation: String?) async throws -> Answer
}

/// The Amin HTTP API (amin/api.py). The session is the server's cookie, kept
/// in the app's own cookie store; nothing else is stored.
nonisolated final class AminClient: Engine {
  let base: URL
  private let session: URLSession

  init(base: URL, session: URLSession = .shared) {
    self.base = base
    self.session = session
  }

  private static let decoder: JSONDecoder = {
    let d = JSONDecoder()
    d.keyDecodingStrategy = .convertFromSnakeCase
    return d
  }()
  private static let encoder: JSONEncoder = {
    let e = JSONEncoder()
    e.keyEncodingStrategy = .convertToSnakeCase
    return e
  }()

  // MARK: transport

  private func send<T: Decodable>(_ method: String, _ path: String, query: [String: String?] = [:],
                                  json: (any Encodable)? = nil, body: Data? = nil,
                                  contentType: String? = nil, as: T.Type = T.self) async throws -> T {
    var parts = URLComponents(url: base.appending(path: path), resolvingAgainstBaseURL: false)!
    let items = query.compactMap { k, v in v.map { URLQueryItem(name: k, value: $0) } }
    if !items.isEmpty { parts.queryItems = items }
    var req = URLRequest(url: parts.url!, timeoutInterval: 180)
    req.httpMethod = method
    if let json {
      req.httpBody = try Self.encoder.encode(json)
      req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    } else if let body {
      req.httpBody = body
      req.setValue(contentType ?? "application/octet-stream", forHTTPHeaderField: "Content-Type")
    }
    let data: Data, response: URLResponse
    do { (data, response) = try await session.data(for: req) }
    catch { throw AminError.unreachable(base.host() ?? base.absoluteString) }
    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
    guard (200..<300).contains(status) else {
      if status == 401 { throw AminError.notSignedIn }
      let detail = (try? Self.decoder.decode(ErrorDetail.self, from: data))?.detail
      throw AminError.server(detail ?? "Amin answered with an error (\(status)).")
    }
    return try Self.decoder.decode(T.self, from: data)
  }

  private struct OK: Decodable {}
  private struct ErrorDetail: Decodable { let detail: String? }

  // MARK: accounts

  struct Setup: Decodable { let firstAccount: Bool }
  private struct Credentials: Encodable { let name: String; let password: String; let invite: String? }
  private struct Named: Decodable { let name: String }

  func setup() async throws -> Setup { try await send("GET", "setup") }
  func signIn(name: String, password: String) async throws {
    _ = try await send("POST", "login", json: Credentials(name: name, password: password, invite: nil), as: Named.self)
  }
  func signUp(name: String, password: String, invite: String?) async throws {
    _ = try await send("POST", "signup", json: Credentials(name: name, password: password, invite: invite), as: Named.self)
  }
  func signOut() async throws { _ = try await send("POST", "logout", as: OK.self) }
  func me() async throws -> Me { try await send("GET", "me") }
  func setPrefs(_ prefs: Prefs) async throws -> Prefs { try await send("PATCH", "me/prefs", json: prefs) }
  func packs() async throws -> [Pack] { try await send("GET", "packs") }
  struct Invite: Decodable { let code: String; let validDays: Int }
  func invite() async throws -> Invite { try await send("POST", "invites") }

  // MARK: asking

  private struct AskBody: Encodable { let question: String; let project: String?; let conversationId: String? }

  func ask(_ question: String, project: String?, conversation: String?) async throws -> Answer {
    try await send("POST", "ask", json: AskBody(question: question, project: project, conversationId: conversation))
  }
  func chunk(_ id: String, project: String?) async throws -> Chunk {
    try await send("GET", "chunks/\(id)", query: ["project": project])
  }

  // MARK: history

  func conversations() async throws -> [ConversationSummary] { try await send("GET", "conversations") }
  func conversation(_ id: String) async throws -> Conversation { try await send("GET", "conversations/\(id)") }
  func deleteConversation(_ id: String) async throws { _ = try await send("DELETE", "conversations/\(id)", as: OK.self) }

  // MARK: documents and projects

  struct Uploaded: Decodable { let document: String; let chunks: Int }
  func upload(_ data: Data, filename: String, to library: Library) async throws -> Uploaded {
    let (lib, pid) = Self.split(library)
    return try await send("POST", "upload", query: ["filename": filename, "library": lib, "project": pid],
                          body: data, contentType: "application/octet-stream")
  }
  func delete(_ filename: String, from library: Library) async throws {
    let (lib, pid) = Self.split(library)
    _ = try await send("DELETE", "documents", query: ["filename": filename, "library": lib, "project": pid], as: OK.self)
  }
  private static func split(_ l: Library) -> (String, String?) {
    switch l {
    case .mine: ("private", nil)
    case .household: ("household", nil)
    case .project(let id): ("project", id)
    }
  }

  private struct NewProject: Encodable { let name: String }
  func createProject(_ name: String) async throws -> Project { try await send("POST", "projects", json: NewProject(name: name)) }
  func deleteProject(_ id: String) async throws { _ = try await send("DELETE", "projects/\(id)", as: OK.self) }

  // MARK: memory

  private struct FactBody: Encodable { let text: String }
  func memory() async throws -> [Fact] { try await send("GET", "memory") }
  func remember(_ text: String) async throws -> Fact { try await send("POST", "memory", json: FactBody(text: text)) }
  func forget(_ id: String) async throws { _ = try await send("DELETE", "memory/\(id)", as: OK.self) }

  // MARK: Amin's own model (ADR-014)

  #if os(iOS) || os(macOS) || os(visionOS)
  func models() async throws -> [ModelInfo] { try await send("GET", "models") }

  /// One model file, downloaded to a temporary location (large: streamed to disk, not memory).
  func modelFile(_ model: String, _ file: String, progress: @escaping @Sendable (Int64) -> Void = { _ in }) async throws -> URL {
    let url = base.appending(path: "models/\(model)/\(file)")
    let (tmp, response) = try await session.download(from: url, delegate: ByteProgress(progress))
    guard (response as? HTTPURLResponse)?.statusCode == 200 else {
      throw AminError.server("Couldn't download \(file) from your Amin computer.")
    }
    return tmp
  }
  #endif

  /// Reports bytes written so a multi-gigabyte file shows real progress.
  private final class ByteProgress: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    let report: @Sendable (Int64) -> Void
    init(_ report: @escaping @Sendable (Int64) -> Void) { self.report = report }
    func urlSession(_ s: URLSession, downloadTask: URLSessionDownloadTask, didWriteData _: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite _: Int64) { report(totalBytesWritten) }
    func urlSession(_ s: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {}
  }

  // MARK: voice

  func transcribe(_ audio: Data, contentType: String, lang: String?) async throws -> Transcript {
    try await send("POST", "transcribe", query: ["lang": lang], body: audio, contentType: contentType)
  }
}
