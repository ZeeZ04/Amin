import Foundation

/// Finds the coding question or error on a screen of OCR text, for live help.
/// Pure text rules, so it costs nothing to run every few seconds; only what it
/// finds is sent to the model.
nonisolated enum LiveDetector {
  struct Found: Equatable, Sendable {
    enum Kind: String, Sendable { case error, task, question }
    let kind: Kind
    /// The line shown on the card as "the question".
    let line: String
    /// Normalised, so the same error on a later capture is not answered twice.
    var key: String { line.lowercased().filter { $0.isLetter || $0 == " " } }
  }

  /// Error lines first: they're the most common reason to look while coding. Then a
  /// task to write code, then a question. For errors the last match wins, because
  /// terminals and logs put the newest at the bottom; a task is usually read top down.
  static func find(in text: String) -> Found? {
    let lines = text.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }
    if let line = lines.last(where: isError) { return Found(kind: .error, line: clip(line)) }
    if let line = lines.first(where: isTask) { return Found(kind: .task, line: clip(line)) }
    if let line = lines.last(where: isQuestion) { return Found(kind: .question, line: clip(line)) }
    return nil
  }

  static func isError(_ line: String) -> Bool {
    guard line.count >= 8 else { return false }
    return line.range(of: errorPattern, options: [.regularExpression, .caseInsensitive]) != nil
  }

  /// A question about code: ends with "?", long enough to mean something, and
  /// uses at least one programming word. Ordinary chat questions are left alone.
  static func isQuestion(_ line: String) -> Bool {
    guard line.hasSuffix("?"), (15...300).contains(line.count) else { return false }
    let words = Set(line.lowercased().split { !$0.isLetter && $0 != "+" && $0 != "#" }.map(String.init))
    return !words.isDisjoint(with: codingWords)
  }

  /// An instruction to write code: "Write a function…", "Implement…", "Given an array…, return…",
  /// or a heading such as "Task 2:" or "Exercise:" followed by a coding word.
  static func isTask(_ line: String) -> Bool {
    guard (15...400).contains(line.count) else { return false }
    let lower = line.lowercased()
    let opens = lower.range(of: taskPattern, options: .regularExpression) != nil
    let given = lower.hasPrefix("given ") && lower.contains("return")
    guard opens || given else { return false }
    let words = Set(lower.split { !$0.isLetter && $0 != "+" && $0 != "#" }.map(String.init))
    return !words.isDisjoint(with: codingWords)
  }

  private static let taskPattern =
    #"^((task|exercise|problem|question|assignment|challenge)\s*\d*\s*[:.)-]\s*|\d+[.)]\s*)?(write|implement|create|build|code|develop|design|define|modify|complete|fix|refactor)\b"#

  private static func clip(_ line: String) -> String { line.count > 160 ? String(line.prefix(157)) + "…" : line }

  private static let errorPattern =
    #"(traceback \(most recent call last\)|^\w*(error|exception)\b[:(]|\berror( \w+)?:|\bfatal( error)?:|\bpanic:|segmentation fault|\bundefined reference\b|cannot find .* in scope|\bnot found\b.*\b(module|command|file)|\bfailed\b.*\b(test|build|compil)|\b(tests?|build) failed\b|uncaught \w+|\bE\d{4}\b)"#

  private static let codingWords: Set<String> = [
    "code", "function", "func", "method", "class", "struct", "variable", "array", "list", "dict", "dictionary",
    "string", "loop", "recursion", "algorithm", "bug", "error", "exception", "compile", "compiler", "debug",
    "python", "swift", "swiftui", "javascript", "typescript", "js", "ts", "java", "kotlin", "c", "c++", "c#",
    "rust", "go", "sql", "query", "regex", "bash", "shell", "git", "api", "json", "http", "react", "node",
    "npm", "pip", "xcode", "async", "await", "thread", "pointer", "null", "nil", "optional", "type",
    "implement", "refactor", "complexity", "o(n)", "test", "tests", "pytest", "database", "endpoint",
    "program", "script", "integer", "integers", "number", "numbers", "input", "output", "return", "returns",
    "parameter", "argument", "app", "view", "component", "table", "file", "sort", "search", "tree", "node",
    "linked", "stack", "queue", "hash", "map", "matrix", "character", "characters", "palindrome", "fibonacci",
  ]
}
