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
  nonisolated static let localModelKey = "amin.localModel"

  /// The on-device model, when one is chosen (ADR-014). With it and no server,
  /// Amin works fully offline: no account, nothing leaves the device.
  private(set) var local: (any Engine)?
  private(set) var localModelName: String?
  var isLocalOnly: Bool { local != nil && client == nil }
  /// Documents kept on this device, answered from with citations by the local model.
  let library: LocalLibrary? = try? LocalLibrary()
  #if os(iOS) || os(macOS) || os(visionOS)
  /// The public Amin account and plan (Supabase + RevenueCat); unused when not configured.
  let account = Account()
  #endif

  init() {
    if let saved = UserDefaults.standard.string(forKey: Self.serverKey), let url = URL(string: saved) {
      client = AminClient(base: url)
    }
    restoreLocalModel()
  }

  // MARK: on-device model

  /// Use the model folder the person chose (security-scoped, remembered across launches).
  func useLocalModel(at folder: URL) throws {
    #if os(iOS) || os(macOS) || os(visionOS)
    let ok = folder.startAccessingSecurityScopedResource()
    defer { if ok { folder.stopAccessingSecurityScopedResource() } }
    #if os(macOS)
    let bookmark = try folder.bookmarkData(options: .withSecurityScope)
    #else
    let bookmark = try folder.bookmarkData()
    #endif
    UserDefaults.standard.set(bookmark, forKey: Self.localModelKey)
    restoreLocalModel()
    if phase == .connect, local != nil { phase = .ready }
    #else
    throw AminError.server("This device cannot run the model; connect to an Amin computer.")
    #endif
  }

  /// A model downloaded into the app's own storage needs no bookmark.
  func useDownloadedModel(at folder: URL) {
    #if os(iOS) || os(macOS) || os(visionOS)
    UserDefaults.standard.removeObject(forKey: Self.localModelKey)
    UserDefaults.standard.set(folder.lastPathComponent, forKey: "amin.downloadedModel")
    local = LocalEngine(directory: folder, library: library)
    localModelName = folder.lastPathComponent
    #endif
  }

  func forgetLocalModel() {
    UserDefaults.standard.removeObject(forKey: "amin.downloadedModel")
    UserDefaults.standard.removeObject(forKey: Self.localModelKey)
    local = nil; localModelName = nil
    if client == nil { phase = .connect }
  }

  private func restoreLocalModel() {
    #if os(iOS) || os(macOS) || os(visionOS)
    if let name = UserDefaults.standard.string(forKey: "amin.downloadedModel") {
      let dir = ModelDownloader.root.appending(path: name, directoryHint: .isDirectory)
      if FileManager.default.fileExists(atPath: dir.appending(path: "config.json").path()) {
        local = LocalEngine(directory: dir, library: library); localModelName = name
        return
      }
    }
    guard let data = UserDefaults.standard.data(forKey: Self.localModelKey) else { return }
    var stale = false
    #if os(macOS)
    let url = try? URL(resolvingBookmarkData: data, options: .withSecurityScope, bookmarkDataIsStale: &stale)
    #else
    let url = try? URL(resolvingBookmarkData: data, bookmarkDataIsStale: &stale)
    #endif
    guard let url else { return }
    _ = url.startAccessingSecurityScopedResource()  // held for the app's lifetime while the model is in use
    local = LocalEngine(directory: url, library: library)
    localModelName = url.lastPathComponent
    #endif
  }

  /// Local when chosen and preferred; otherwise the Amin computer.
  var preferLocal: Bool {
    get { UserDefaults.standard.object(forKey: "amin.preferLocal") as? Bool ?? true }
    set { UserDefaults.standard.set(newValue, forKey: "amin.preferLocal") }
  }
  var engine: (any Engine)? {
    #if targetEnvironment(simulator)
    // The model cannot run in the Simulator (no Metal for MLX): use the Amin computer when there is one.
    return client ?? local
    #else
    return (preferLocal ? local : nil) ?? client ?? local
    #endif
  }

  var serverURL: URL? { client?.base }
  var project: Project? { me?.projects.first { $0.id == space } }
  var isBusy: Bool { turns.last.map { $0.answer == nil && $0.failed == nil } ?? false }

  // MARK: connecting

  /// On launch: a saved server with a live session goes straight in.
  func resume() async {
    #if os(iOS) || os(macOS) || os(visionOS)
    await account.restore()
    #endif
    guard client != nil else {
      if local != nil || hasAccount { phase = .ready }  // on-device, with or without an account
      return
    }
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

  var hasAccount: Bool {
    #if os(iOS) || os(macOS) || os(visionOS)
    account.isSignedIn
    #else
    false
    #endif
  }

  /// Signed in to an Amin account: the app runs on this device from here.
  func accountSignedIn() async {
    phase = .ready
  }

  #if os(iOS) || os(macOS) || os(visionOS)
  func signOutOfAccount() async {
    await account.signOut()
    if client == nil { turns = []; conversationID = nil; phase = .connect }
  }
  #endif

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
    guard !q.isEmpty, !isBusy, let engine else { return nil }
    turns.append(Turn(question: q))
    let index = turns.count - 1
    do {
      let a = try await engine.ask(q, project: space.isEmpty ? nil : space, conversation: conversationID)
      turns[index].answer = a
      if let client, a.conversationId != nil {
        let isNew = conversationID != a.conversationId
        conversationID = a.conversationId
        if isNew { conversations = (try? await client.conversations()) ?? conversations }
      }
      return a
    } catch {
      turns[index].failed = error.localizedDescription
      return nil
    }
  }

  func source(_ chunkID: String) async throws -> Chunk {
    if let c = library?.chunk(chunkID) { return c }  // cited from this device's own library
    guard let client else { throw AminError.notSignedIn }
    return try await client.chunk(chunkID, project: space.isEmpty ? nil : space)
  }
}
