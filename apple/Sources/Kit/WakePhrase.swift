import Foundation

/// "Hey Amin" / "Hey Ameen" in what an on-device recogniser heard (Task 2).
/// Apple's English recogniser often spells the name "Ameen", "Amine",
/// "a man" or "amen", so those count, but only right after a greeting, so that
/// "Amina called" or "I mean it" do not wake Amin (the same rule as the server's
/// amin/voice.py WAKE, E37).
nonisolated enum WakePhrase {
  static func matches(_ heard: String) -> Bool {
    heard.lowercased().range(
      of: #"\b(hey|hi|hello|ok|okay)[\s,]+(a{1,2}mee?n|amine?|a man|amen)\b(?!a)"#,
      options: .regularExpression) != nil
  }
}
