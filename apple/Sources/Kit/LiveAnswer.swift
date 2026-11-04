import Foundation

/// Splits a live-help reply into its numbered steps and its answer. The model is
/// asked for "Steps:" then "Answer:"; a reply without them is all answer.
nonisolated struct LiveAnswer: Equatable, Sendable {
  var steps: [String]
  var answer: String
  /// True when the answer holds a code block, shown in a monospaced font without the fences.
  var isCode: Bool

  init(_ reply: String) {
    let lines = reply.components(separatedBy: "\n")
    let answerAt = lines.firstIndex { Self.isHeading($0, "answer") }
    let hasSteps = lines.contains { Self.isHeading($0, "steps") }
    let stepLines = lines[..<(answerAt ?? (hasSteps ? lines.count : 0))].filter { !Self.isHeading($0, "steps") }
    steps = stepLines.compactMap(Self.step)
    let rest = answerAt.map { i -> [String] in
      var first = lines[i].replacingOccurrences(of: #"^[\s*#]*answer[\s*]*:[\s*]*"#, with: "",
                                                options: [.regularExpression, .caseInsensitive])
      first = first.trimmingCharacters(in: .whitespaces)
      return (first.isEmpty ? [] : [first]) + lines[(i + 1)...]
    } ?? (hasSteps ? [] : lines)
    isCode = rest.contains { $0.hasPrefix("```") }
    answer = rest.filter { !$0.hasPrefix("```") }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private static func isHeading(_ line: String, _ word: String) -> Bool {
    line.range(of: #"^[\s*#]*\#(word)[\s*]*:"#, options: [.regularExpression, .caseInsensitive]) != nil
  }

  /// "1. Do this", "- Do this", "**2.** Do this" become "Do this"; blank lines are dropped.
  private static func step(_ line: String) -> String? {
    let t = line.replacingOccurrences(of: #"^\s*(\*\*)?(\d+[.)]|[-•*])(\*\*)?\s*"#, with: "", options: .regularExpression)
      .trimmingCharacters(in: .whitespaces)
    return t.isEmpty ? nil : t
  }
}
