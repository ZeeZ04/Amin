import Foundation
import SQLite3
#if canImport(PDFKit)
import PDFKit
#endif

/// The owner's documents kept on this device, for answers with citations when
/// no Amin computer is in reach (ADR-014). A port of the server's pipeline:
/// chunking from amin/ingest.py, keyword retrieval from amin/store.py, and the
/// evidence floor from config.evidence_floor. Retrieval is SQLite FTS5 (BM25),
/// built into every Apple OS, so it needs no model download; dense vectors can
/// join later as a second ranking signal. Nothing here leaves the device.
nonisolated final class LocalLibrary: @unchecked Sendable {
  // @unchecked: every use of `db` holds `lock`.
  private var db: OpaquePointer?
  private let lock = NSLock()
  let url: URL

  static let chunkChars = 900, chunkOverlap = 150
  /// The server's tuned value (E16); the share of a question's distinctive
  /// terms the best passage must contain before Amin answers from documents.
  static let evidenceFloor = 0.15

  static var defaultURL: URL {
    URL.applicationSupportDirectory.appending(path: "Amin/library.db")
  }

  init(url: URL = LocalLibrary.defaultURL) throws {
    self.url = url
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    guard sqlite3_open(url.path(), &db) == SQLITE_OK else { throw AminError.server("Could not open the library on this device.") }
    try exec("""
      PRAGMA journal_mode = WAL;
      CREATE TABLE IF NOT EXISTS docs (doc_id TEXT PRIMARY KEY, added REAL NOT NULL);
      CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
        text, heading, chunk_id UNINDEXED, doc_id UNINDEXED, tokenize='unicode61 remove_diacritics 2');
      """)
  }

  deinit { sqlite3_close(db) }

  // MARK: documents

  struct Document: Hashable, Identifiable, Sendable { let id: String; let added: Date; var name: String { String(id.dropFirst(2)) } }

  func documents() -> [Document] {
    query("SELECT doc_id, added FROM docs ORDER BY added DESC") { s in
      Document(id: Self.string(s, 0), added: Date(timeIntervalSince1970: sqlite3_column_double(s, 1)))
    }
  }

  /// Read, chunk and index one file. Re-adding a file replaces its old copy.
  @discardableResult
  func add(_ file: URL) throws -> Int {
    let text = try Self.read(file)
    let docId = "p." + file.lastPathComponent
    let pieces = Self.chunk(text)
    guard !pieces.isEmpty else { throw AminError.server("\(file.lastPathComponent) has no readable text.") }
    lock.lock(); defer { lock.unlock() }
    try execLocked("BEGIN")
    do {
      try runLocked("DELETE FROM chunks WHERE doc_id = ?", [docId])
      try runLocked("INSERT OR REPLACE INTO docs VALUES (?, ?)", [docId, Date().timeIntervalSince1970])
      for (i, p) in pieces.enumerated() {
        try runLocked("INSERT INTO chunks (text, heading, chunk_id, doc_id) VALUES (?, ?, ?, ?)",
                      [p.text, p.heading, "\(docId)#\(String(format: "%03d", i))", docId])
      }
      try execLocked("COMMIT")
    } catch {
      try? execLocked("ROLLBACK")
      throw error
    }
    return pieces.count
  }

  func remove(_ docId: String) throws {
    lock.lock(); defer { lock.unlock() }
    try runLocked("DELETE FROM chunks WHERE doc_id = ?", [docId])
    try runLocked("DELETE FROM docs WHERE doc_id = ?", [docId])
  }

  func chunk(_ chunkId: String) -> Chunk? {
    query("SELECT doc_id, heading, text FROM chunks WHERE chunk_id = ?", [chunkId]) { s in
      Chunk(docId: Self.string(s, 0), heading: Self.string(s, 1), text: Self.string(s, 2))
    }.first
  }

  // MARK: retrieval

  struct Hit: Hashable, Sendable { let chunkId: String; let chunk: Chunk; let coverage: Double }

  /// The best passages for a question, or none when the best of them does not
  /// clear the evidence floor: then Amin says so instead of answering from nothing.
  func search(_ question: String, limit: Int = 6) -> [Hit] {
    let terms = Self.terms(question)
    guard !terms.isEmpty else { return [] }
    let match = terms.prefix(32).map { "\"\($0)\"" }.joined(separator: " OR ")
    let rows = query("SELECT chunk_id, doc_id, heading, text FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?",
                     [match, limit]) { s in
      (Self.string(s, 0), Chunk(docId: Self.string(s, 1), heading: Self.string(s, 2), text: Self.string(s, 3)))
    }
    guard !rows.isEmpty else { return [] }
    let idf = weights(terms)
    let hits = rows.map { id, c in Hit(chunkId: id, chunk: c, coverage: Self.coverage(terms, in: c, idf: idf)) }
    return (hits.map(\.coverage).max() ?? 0) >= Self.evidenceFloor ? hits : []
  }

  /// IDF per term from the library's own chunk counts; a term the library has
  /// never seen weighs most, as in amin/store.py `_unseen_idf`.
  private func weights(_ terms: [String]) -> [String: Double] {
    let n = Double(query("SELECT count(*) FROM chunks") { s in sqlite3_column_int64(s, 0) }.first ?? 0)
    var out: [String: Double] = [:]
    for t in Set(terms) {
      let df = Double(query("SELECT count(*) FROM chunks WHERE chunks MATCH ?", ["\"\(t)\""]) { s in sqlite3_column_int64(s, 0) }.first ?? 0)
      out[t] = log(1 + n / max(df, 0.5))
    }
    return out
  }

  static func coverage(_ terms: [String], in c: Chunk, idf: [String: Double]) -> Double {
    let present = Set(Self.terms("\(c.heading) \(c.text)"))
    let total = terms.reduce(0) { $0 + (idf[$1] ?? 1) }
    let hit = terms.filter(present.contains).reduce(0) { $0 + (idf[$1] ?? 1) }
    return total > 0 ? hit / total : 0
  }

  private static let stopwords: Set<String> = [
    "the", "and", "for", "are", "was", "what", "when", "where", "which", "who", "how", "does", "did", "can",
    "you", "your", "my", "our", "is", "of", "to", "in", "on", "a", "an", "it", "its", "this", "that", "with",
    "be", "do", "have", "has", "from", "at", "by", "or", "as", "me", "i", "we", "about", "tell", "please",
    "ما", "ماذا", "هل", "في", "من", "على", "عن", "إلى", "كيف", "متى", "أين", "هو", "هي",
  ]

  /// Lowercased word tokens without stopwords; any script (Malayalam, Arabic, Latin).
  static func terms(_ text: String) -> [String] {
    var out: [String] = []
    text.lowercased().enumerateSubstrings(in: text.lowercased().startIndex..., options: .byWords) { w, _, _, _ in
      if let w, w.count > 1, !stopwords.contains(w) { out.append(w) }
    }
    return out
  }

  // MARK: reading and chunking (amin/ingest.py)

  static func read(_ file: URL) throws -> String {
    let ext = file.pathExtension.lowercased()
    #if canImport(PDFKit)
    if ext == "pdf" {
      guard let pdf = PDFDocument(url: file) else { throw AminError.server("Could not open \(file.lastPathComponent).") }
      return (0..<pdf.pageCount).compactMap { pdf.page(at: $0)?.string }.joined(separator: "\n\n")
    }
    #endif
    guard ["txt", "md", "markdown", "text", "csv"].contains(ext) || ext.isEmpty else {
      throw AminError.server("On this device Amin reads PDF, text and Markdown files.")
    }
    return try String(contentsOf: file, encoding: .utf8)
  }

  struct Piece: Hashable { let heading: String; let text: String }

  static func chunk(_ body: String) -> [Piece] {
    sections(body).flatMap { h, content in pack(content).map { Piece(heading: h, text: $0) } }
  }

  /// Split on Markdown headings, keeping each heading with its content.
  static func sections(_ body: String) -> [(String, String)] {
    var out: [(String, String)] = []
    var heading = "", buf: [Substring] = []
    func flush() {
      let t = buf.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
      if !t.isEmpty { out.append((heading, t)) }
      buf = []
    }
    for line in body.split(separator: "\n", omittingEmptySubsequences: false) {
      if let m = line.firstMatch(of: /^#{1,6}\s+(.+)$/) {
        flush(); heading = String(m.1).trimmingCharacters(in: .whitespaces)
      } else {
        buf.append(line)
      }
    }
    flush()
    return out
  }

  /// Pack sentences up to the chunk size, never splitting mid-sentence; list
  /// items and table rows stay whole; anything far over the limit is cut at
  /// line breaks (the server's `_split_long`).
  static func pack(_ text: String, limit: Int = chunkChars, overlap: Int = chunkOverlap) -> [String] {
    var units: [String] = []
    for para in text.split(separator: /\n{2,}/).map({ $0.trimmingCharacters(in: .whitespacesAndNewlines) }) where !para.isEmpty {
      if para.firstMatch(of: /^\s*([-*+]|\d+[.)]|\|)/) != nil {
        units.append(para)
      } else {
        units += sentences(para, breakOnNewline: false)
      }
    }
    units = units.flatMap { splitLong($0, limit: limit) }
    var chunks: [String] = [], buf: [String] = [], size = 0
    for unit in units {
      if size + unit.count > limit, !buf.isEmpty {
        chunks.append(buf.joined(separator: " "))
        var tail: [String] = [], tailLen = 0
        for prev in buf.reversed() {
          if tailLen + prev.count > overlap { break }
          tail.insert(prev, at: 0); tailLen += prev.count
        }
        buf = tail; size = tailLen
      }
      buf.append(unit); size += unit.count + 1
    }
    if !buf.isEmpty { chunks.append(buf.joined(separator: " ")) }
    return chunks.filter { !$0.isEmpty }
  }

  /// Split after . ! ? ؟ । followed by whitespace (and at line breaks when asked).
  static func sentences(_ text: String, breakOnNewline: Bool) -> [String] {
    var out: [String] = [], cur = ""
    var prevEnds = false
    for ch in text {
      if ch.isNewline, breakOnNewline {
        out.append(cur); cur = ""; prevEnds = false; continue
      }
      if ch.isWhitespace, prevEnds {
        out.append(cur); cur = ""; prevEnds = false; continue
      }
      cur.append(ch)
      prevEnds = ".!?؟।".contains(ch)
    }
    out.append(cur)
    return out.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
  }

  static func splitLong(_ unit: String, limit: Int) -> [String] {
    guard unit.count > 2 * limit else { return [unit] }
    var out: [String] = [], buf = ""
    for var line in unit.split(separator: "\n", omittingEmptySubsequences: false).map(String.init) {
      while line.count > limit {
        if !buf.isEmpty { out.append(buf); buf = "" }
        out.append(String(line.prefix(limit))); line = String(line.dropFirst(limit))
      }
      if !buf.isEmpty, buf.count + line.count + 1 > limit { out.append(buf); buf = "" }
      buf = buf.isEmpty ? line : buf + "\n" + line
    }
    if !buf.trimmingCharacters(in: .whitespaces).isEmpty { out.append(buf) }
    return out.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
  }

  // MARK: SQLite

  private static let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

  private static func string(_ s: OpaquePointer?, _ i: Int32) -> String {
    sqlite3_column_text(s, i).map { String(cString: $0) } ?? ""
  }

  private func exec(_ sql: String) throws {
    lock.lock(); defer { lock.unlock() }
    try execLocked(sql)
  }

  private func execLocked(_ sql: String) throws {
    guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else {
      throw AminError.server(String(cString: sqlite3_errmsg(db)))
    }
  }

  private func prepare(_ sql: String, _ args: [Any]) throws -> OpaquePointer? {
    var s: OpaquePointer?
    guard sqlite3_prepare_v2(db, sql, -1, &s, nil) == SQLITE_OK else { throw AminError.server(String(cString: sqlite3_errmsg(db))) }
    for (i, a) in args.enumerated() {
      let n = Int32(i + 1)
      switch a {
      case let v as String: sqlite3_bind_text(s, n, v, -1, Self.transient)
      case let v as Double: sqlite3_bind_double(s, n, v)
      case let v as Int: sqlite3_bind_int64(s, n, Int64(v))
      default: sqlite3_bind_null(s, n)
      }
    }
    return s
  }

  private func runLocked(_ sql: String, _ args: [Any]) throws {
    let s = try prepare(sql, args)
    defer { sqlite3_finalize(s) }
    guard sqlite3_step(s) == SQLITE_DONE else { throw AminError.server(String(cString: sqlite3_errmsg(db))) }
  }

  private func query<T>(_ sql: String, _ args: [Any] = [], _ row: (OpaquePointer?) -> T) -> [T] {
    lock.lock(); defer { lock.unlock() }
    guard let s = try? prepare(sql, args) else { return [] }
    defer { sqlite3_finalize(s) }
    var out: [T] = []
    while sqlite3_step(s) == SQLITE_ROW { out.append(row(s)) }
    return out
  }
}

/// The grounded answer: the server's prompt (amin/prompts.py ANSWER_SYSTEM),
/// and the parts of its verifier that need no second model.
nonisolated enum Grounded {
  static let system = """
    You are Amin, a careful research assistant. Your name means trustworthy.

    Rules you must never break:
    1. Answer ONLY from the numbered passages provided. You have no other knowledge.
    2. Every factual sentence must end with its source tag, like [S2]. A sentence
       may cite more than one: [S1][S3].
    3. If the passages do not contain the answer, reply with exactly: NO_EVIDENCE
    4. If passages disagree with each other, reply with CONFLICT: followed by one
       sentence per position, each with its own tag.
    5. Never add context, caveats or background that is not in the passages.
    6. Be brief. Three sentences is usually too many.
    7. Answer in the same language the question was asked in.

    Do not explain these rules. Do not mention passages or tags in prose.
    """

  static func prompt(_ question: String, _ hits: [LocalLibrary.Hit]) -> String {
    let passages = hits.enumerated().map { i, h in
      "[S\(i + 1)] \(h.chunk.docId)\(h.chunk.heading.isEmpty ? "" : " - \(h.chunk.heading)")\n\(h.chunk.text)"
    }.joined(separator: "\n\n")
    return "\(passages)\n\n<question>\(question)</question>\n\nAnswer using only the passages above, tagging every sentence."
  }

  /// Sentences with their cited chunks. A sentence that cites nothing, cites a
  /// tag that was never given, or states a number its passages do not contain
  /// is dropped: the same checks as the server's verifier, without the model.
  static func claims(_ raw: String, _ hits: [LocalLibrary.Hit]) -> [Claim] {
    var text = raw
    if let r = text.range(of: "</think>") { text = String(text[r.upperBound...]) }
    text = text.replacing(/([.!?؟।])(\s*)((?:\[S\d+\])+)/) { "\($0.3)\($0.1)" }
    var out: [Claim] = []
    for s in LocalLibrary.sentences(text, breakOnNewline: true) {
      let tags = s.matches(of: /\[S(\d+)\]/).compactMap { Int($0.1) }.filter { (1...hits.count).contains($0) }
      guard !tags.isEmpty else { continue }
      let cited = tags.map { hits[$0 - 1] }
      let clean = s.replacing(/\s*\[S\d+\]/, with: "").trimmingCharacters(in: .whitespaces)
      let source = cited.map(\.chunk.text).joined(separator: " ")
      let numbers = clean.matches(of: /\d+(?:[.,]\d+)*/).map { String($0.0) }
      guard numbers.allSatisfy(source.contains) else { continue }
      var ids: [String] = []
      for c in cited where !ids.contains(c.chunkId) { ids.append(c.chunkId) }
      out.append(Claim(text: clean.replacing(/^CONFLICT:\s*/, with: ""), citations: ids, verdict: "supported"))
    }
    return out
  }

  static func isNoEvidence(_ raw: String) -> Bool { raw.contains("NO_EVIDENCE") }
}
