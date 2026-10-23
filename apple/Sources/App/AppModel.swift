import Foundation
import Observation

/// Everything the screens share. Main-actor (the module default): views read
/// it directly; network calls suspend without leaving the main actor, because
/// URLSession does the waiting.
@Observable
final class AppModel {
  enum Phase: Equatable { case connect, ready }

  private(set) var phase: Phase = .connect
  private(set) var client: AminClient?
  private(set) var me: Me?
  private(set) var conversations: [ConversationSummary] = []

  /// The open conversation, oldest first. A turn whose answer is nil is in flight.
  private(set) var turns: [Turn] = []
  private(set) var conversationID: String?
  /// "" is general chat; otherwise a project id.
  var space: String = ""
  var error: String?

  struct Turn: Identifiable, Hashable {
    let id = UUID()
    let question: String
    var answer: Answer?
    var failed: String?
  }

  nonisolated static let serverKey = "amin.server"

  init() {
    if let saved = UserDefaults.standard.string(forKey: Self.serverKey), let url = URL(string: saved) {
      client = AminClient(base: url)
    }
  }

  var serverURL: URL? { client?.base }
  var project: Project? { me?.projects.first { $0.id == space } }
  var isBusy: Bool { turns.last.map { $0.answer == nil && $0.failed == nil } ?? false }

  // MARK: connecting

  /// On launch: a saved server with a live session goes straight in.
  func resume() async {
    guard client != nil else { return }
    do { try await refresh(); phase = .ready } catch { phase = .connect }
  }

  func connect(to address: String) throws -> AminClient {
    var text = address.trimmingCharacters(in: .whitespaces)
    if !text.contains("://") { text = "http://" + text }
    guard let url = URL(string: text), url.host() != nil else {
      throw AminError.server("That doesn't look like an address. Try the one `make serve` printed, like 192.168.1.20:8000.")
    }
    let c = AminClient(base: url)
    client = c
    UserDefaults.standard.set(url.absoluteString, forKey: Self.serverKey)
    return c
  }

  func signedIn() async throws {
    try await refresh()
    phase = .ready
  }

  func signOut() async {
    try? await client?.signOut()
    me = nil; conversations = []; turns = []; conversationID = nil; space = ""
    phase = .connect
  }

  func refresh() async throws {
    guard let client else { throw AminError.notSignedIn }
    me = try await client.me()
    conversations = (try? await client.conversations()) ?? []
    if !space.isEmpty, project == nil { space = "" }
  }

  // MARK: conversation

  func newChat(in space: String? = nil) {
    turns = []; conversationID = nil
    if let space { self.space = space }
  }

  func open(_ id: String) async {
    guard let client else { return }
    do {
      let c = try await client.conversation(id)
      conversationID = c.id
      space = c.project.flatMap { p in me?.projects.contains { $0.id == p } == true ? p : nil } ?? ""
      turns = c.messages.map { Turn(question: $0.question, answer: $0.answer) }
    } catch { self.error = error.localizedDescription }
  }

  func delete(_ id: String) async {
    try? await client?.deleteConversation(id)
    if id == conversationID { newChat() }
    conversations.removeAll { $0.id == id }
  }

  /// Ask in the current space and conversation. Returns the answer for voice mode.
  @discardableResult
  func ask(_ question: String) async -> Answer? {
    let q = question.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !q.isEmpty, !isBusy, let client else { return nil }
    turns.append(Turn(question: q))
    let index = turns.count - 1
    do {
      let a = try await client.ask(q, project: space.isEmpty ? nil : space, conversation: conversationID)
      turns[index].answer = a
      let isNew = conversationID != a.conversationId
      conversationID = a.conversationId
      if isNew { conversations = (try? await client.conversations()) ?? conversations }
      return a
    } catch {
      turns[index].failed = error.localizedDescription
      return nil
    }
  }

  func source(_ chunkID: String) async throws -> Chunk {
    guard let client else { throw AminError.notSignedIn }
    return try await client.chunk(chunkID, project: space.isEmpty ? nil : space)
  }
}
